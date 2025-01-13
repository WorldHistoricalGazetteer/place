# /gis/intersections.py

import json
import logging

from shapely.geometry.geo import shape
from shapely.validation import explain_validity

from .utils import get_valid_geom, vespa_bbox
from ..config import VespaClient

logger = logging.getLogger(__name__)


class GeometryIntersect:
    """

    """

    def __init__(self, geometry=None, geom=None, bbox=None, schema=None, fields=None) -> None:
        """
        Initializes the resolver with a geometry and bounding box.

        Args:
            geometry (dict): The GeoJSON geometry to check against.
            bbox (dict): A bounding box dictionary with keys "bbox_sw_lat", "bbox_sw_lng", "bbox_ne_lat", "bbox_ne_lng".
            schema (str, optional): Vespa schema to query. Defaults to "iso3166".
            fields (str, optional): Comma-separated list of fields to query. Defaults to "code2".
        """

        # Validate and set geometry: geom is assumed to have been pre-validated
        if geom:
            self.geom = geom
        elif geometry:
            self.geom = get_valid_geom(geometry)

        # Derive bounding box if not provided
        self.bbox = bbox or (vespa_bbox(self.geom) if self.geom else None)
        self.vespa_client = VespaClient()
        self.schema = schema or "iso3166"
        self.fields = fields or "code2"

    def resolve(self) -> list:
        """
        """
        if not self.geom or not self.bbox:
            logger.warning("Cannot find intersections: missing geometry or bounding box.")
            return []

        try:
            candidates = BoxIntersect(self.bbox, schema=self.schema, fields=self.fields).box_intersect()

            results = set()
            for candidate in candidates:
                if 'geometry' in candidate:
                    candidate_geom = shape(json.loads(candidate['geometry']))

                    # Check validity of candidate geometry
                    if not candidate_geom.is_valid:
                        logger.info(f"Invalid geometry found: {candidate['code2']}: {explain_validity(candidate_geom)}")
                        # Try to fix the geometry
                        candidate_geom = candidate_geom.buffer(0)
                        if not candidate_geom.is_valid:
                            logger.info(f"Could not fix geometry for {candidate['code2']}")
                            continue

                    if self.geom.intersects(candidate_geom):
                        # Exclude the 'geometry' field and convert the candidate to a tuple of key-value pairs (hashable)
                        results.add(frozenset({k: v for k, v in candidate.items() if k != 'geometry'}.items()))

            # Convert frozensets back to dictionaries and sort by the specified key
            return sorted([dict(frozenset_item) for frozenset_item in results],
                                    key=lambda x: x.get(self.fields.split(',')[0], ''))
        except Exception as e:
            logger.error(f"Error finding intersections: {e}", exc_info=True)
            return []


class BoxIntersect:
    """
    Perform a spatial query in Vespa to find documents whose bounding box intersects
    with the provided bounding box. The Vespa schema and fields to query are configurable: the default values
    are for ISO 3166 country codes.
    """

    def __init__(self, bbox, schema=None, fields=None) -> None:
        """
        Initializes the BoxIntersect with bounding box coordinates and optional schema/fields.

        Args:
            min_lng (float): Minimum longitude of the bounding box.
            min_lat (float): Minimum latitude of the bounding box.
            max_lng (float): Maximum longitude of the bounding box.
            max_lat (float): Maximum latitude of the bounding box.
            schema (str, optional): Vespa schema to query. Defaults to "iso3166".
            fields (str, optional): Fields to query. Defaults to "code2".
        """
        self.min_lng = bbox.get("bbox_sw_lng", -180)
        self.min_lat = bbox.get("bbox_sw_lat", -90)
        self.max_lng = bbox.get("bbox_ne_lng", 180)
        self.max_lat = bbox.get("bbox_ne_lat", 90)
        self.schema = schema or "iso3166"
        self.fields = fields or "code2"

    def box_intersect(self) -> list:
        """
        Perform a Vespa query to find intersecting documents.

        Returns:
            list: A list of documents whose bounding boxes intersect with the provided bounding box.
        """
        try:
            with VespaClient.sync_context("feed") as sync_app:
                query = self._generate_bounding_box_query()
                logger.info(f"Performing Vespa query: {query}")
                response = sync_app.query(query).json
                if "error" in response:
                    raise ValueError(f"Error during Vespa query: {response['error']}")
                return [child.get("fields", {}) for child in response.get("root", {}).get("children", [])]

        except Exception as e:
            raise ValueError(f"Error during Vespa query: {str(e)}") from e

    def _generate_bounding_box_query(self) -> dict:
        """
        Generate the YQL query to check bounding boxes for spatial intersections.

        Returns:
            dict: The YQL query for bounding box intersection.
        """

        def _generate_longitude_conditions() -> str:
            if (self.min_lng <= self.max_lng):
                # Test box does not cross the antimeridian
                # 1. SW corner of document box is within bounds of test box
                # 2. NE corner of document box is within bounds of test box
                # 3. Document box does not cross the antimeridian, but encompasses the test box
                # 4. Document box crosses the antimeridian and encompasses the test box
                return f"""
                    (
                        range(bbox_sw_lng, {self.min_lng}, {self.max_lng})
                        or
                        range(bbox_ne_lng, {self.min_lng}, {self.max_lng})
                        or
                        (
                            bbox_antimeridial = false
                            and
                            bbox_sw_lng < {self.min_lng}
                            and
                            bbox_ne_lng > {self.max_lng}
                        )
                        or
                        (
                            bbox_antimeridial = true
                            and
                            bbox_sw_lng < {self.min_lng}
                            and
                            bbox_ne_lng < {self.min_lng}
                        )
                    )
                """
            else:
                # Test box crosses the antimeridian
                # 1. SW corner of document box is within bounds of test box
                # 2. NE corner of document box is within bounds of test box
                # 3. Document box encompasses the test box (also crossing the meridian)
                return f"""
                    (
                        (
                            range(bbox_sw_lng, {self.min_lng}, 180)
                            or
                            range(bbox_sw_lng, -180, {self.max_lng})
                        )
                        or
                        (
                            range(bbox_ne_lng, {self.min_lng}, 180)
                            or
                            range(bbox_ne_lng, -180, {self.max_lng})
                        )
                        or
                        (
                            bbox_antimeridial = true
                            and
                            bbox_sw_lng < {self.min_lng}
                            and
                            bbox_ne_lng > {self.max_lng}
                        )
                    )
                """

        def _generate_latitude_conditions() -> str:
            # 1. SW corner of document box is within bounds of test box
            # 2. NE corner of document box is within bounds of test box
            # 3. Document box encompasses the test box
            return f"""
                (
                    range(bbox_sw_lat, {self.min_lat}, {self.max_lat})
                    or
                    range(bbox_ne_lat, {self.min_lat}, {self.max_lat})
                    or
                    (
                        bbox_sw_lat < {self.min_lat}
                        and
                        bbox_ne_lat > {self.max_lat}
                    )
                )
            """

        longitude_conditions = _generate_longitude_conditions()
        latitude_conditions = _generate_latitude_conditions()

        return {
            "yql": f"""
                select {self.fields}, geometry from sources {self.schema}
                where
                {longitude_conditions}
                and
                {latitude_conditions}
            """
        }
