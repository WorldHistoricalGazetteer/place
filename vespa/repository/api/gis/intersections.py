# /gis/intersections.py

import json
import logging

from shapely.geometry.geo import shape

from .utils import get_valid_geom, vespa_bbox
from ..config import VespaClient

logger = logging.getLogger(__name__)


class GeometryIntersect:
    """

    """

    def __init__(self, geometry=None, geom=None, bbox=None, namespace=None, schema=None, fields=None) -> None:
        """
        Initializes the resolver with a geometry and bounding box.

        Args:
            geometry (dict): The GeoJSON geometry to check against.
            geom (shapely.geometry.base.BaseGeometry): The Shapely geometry object to check against.
            bbox (dict): A bounding box dictionary with keys "bbox_sw_lat", "bbox_sw_lng", "bbox_ne_lat", "bbox_ne_lng", and "bbox_antimeridial".
            namespace (str, optional): Vespa namespace to query. Defaults to "iso3166".
            schema (str, optional): Vespa schema to query. Defaults to "place".
            fields (str, optional): Comma-separated list of fields to query. Defaults to "code2".
        """

        # Validate and set geometry: geom is assumed to have been pre-validated
        if geom:
            self.geom = geom
        elif geometry:
            self.geom, _ = get_valid_geom(geometry)

        # Derive bounding box if not provided
        self.bbox = bbox or (vespa_bbox(self.geom) if self.geom else None)
        self.vespa_client = VespaClient()
        self.schema = schema or "place"
        self.namespace = namespace or "iso3166"
        self.fields = fields or "meta"
        # logger.info(f"Initialized GeometryIntersect: {self.__dict__}")

    def resolve(self) -> list:
        """
        """
        if not self.geom or not self.bbox:
            logger.warning("Cannot find intersections: missing geometry or bounding box.")
            return []

        try:
            candidates = BoxIntersect(self.bbox, namespace=self.namespace, schema=self.schema,
                                      fields=self.fields).box_intersect()

            # logger.info(f"Found {len(candidates)} candidates for intersection")
            results = set()
            for candidate in candidates:
                # Loop through each candidate's locations
                for location in candidate.get('locations', []):
                    # Check if the location's geometry intersects with the input geometry
                    candidate_geom = shape(json.loads(location['geometry']))
                    if self.geom.intersects(candidate_geom):
                        # Exclude the 'geometry' field and convert the candidate to a tuple of key-value pairs (hashable)
                        results.add(frozenset({k: v for k, v in candidate.items() if k != 'locations'}.items()))

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

    def __init__(self, bbox, namespace=None, schema=None, fields=None) -> None:
        """
        Initializes the BoxIntersect with bounding box coordinates and optional schema/fields.

        Args:
            min_lng (float): Minimum longitude of the bounding box.
            min_lat (float): Minimum latitude of the bounding box.
            max_lng (float): Maximum longitude of the bounding box.
            max_lat (float): Maximum latitude of the bounding box.
            schema (str, optional): Vespa schema to query. Defaults to "place".
            fields (str, optional): Fields to query. Defaults to "meta".
        """
        self.sw_lng = bbox.get("bbox_sw_lng", -180)
        self.sw_lat = bbox.get("bbox_sw_lat", -90)
        self.ne_lng = bbox.get("bbox_ne_lng", 180)
        self.ne_lat = bbox.get("bbox_ne_lat", 90)
        self.antimeridial = bbox.get("bbox_antimeridial", False)
        self.schema = schema or "place"
        self.namespace = namespace or "iso3166"
        self.fields = fields or "meta"
        # logger.info(f"Initialized BoxIntersect: {self.__dict__}")

    def box_intersect(self) -> list:
        """
        Perform a Vespa query to find intersecting documents.

        Returns:
            list: A list of documents whose bounding boxes intersect with the provided bounding box.
        """
        try:
            with VespaClient.sync_context("feed") as sync_app:
                query = self._generate_bounding_box_query()
                # logger.info(f"Performing Vespa query: {query}")
                response = sync_app.query(
                    query,
                    namespace=self.namespace,
                    schema=self.schema,
                ).json
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
            if not self.antimeridial:
                # Test box does not cross the antimeridian
                # 1. SW corner of document box is within bounds of test box
                # 2. NE corner of document box is within bounds of test box
                # 3. Document box does not cross the antimeridian, but encompasses the test box
                # 4. Document box crosses the antimeridian and encompasses the test box
                return f"""
                    (
                        range(bbox_sw_lng, {self.sw_lng}, {self.ne_lng})
                        or
                        range(bbox_ne_lng, {self.sw_lng}, {self.ne_lng})
                        or
                        (
                            bbox_antimeridial = false
                            and
                            bbox_sw_lng < {self.sw_lng}
                            and
                            bbox_ne_lng > {self.ne_lng}
                        )
                        or
                        (
                            bbox_antimeridial = true
                            and
                            bbox_sw_lng < {self.sw_lng}
                            and
                            bbox_ne_lng < {self.sw_lng}
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
                            range(bbox_sw_lng, {self.sw_lng}, 180)
                            or
                            range(bbox_sw_lng, -180, {self.ne_lng})
                        )
                        or
                        (
                            range(bbox_ne_lng, {self.sw_lng}, 180)
                            or
                            range(bbox_ne_lng, -180, {self.ne_lng})
                        )
                        or
                        (
                            bbox_antimeridial = true
                            and
                            bbox_sw_lng < {self.sw_lng}
                            and
                            bbox_ne_lng > {self.ne_lng}
                        )
                    )
                """

        def _generate_latitude_conditions() -> str:
            # 1. SW corner of document box is within bounds of test box
            # 2. NE corner of document box is within bounds of test box
            # 3. Document box encompasses the test box
            return f"""
                (
                    range(bbox_sw_lat, {self.sw_lat}, {self.ne_lat})
                    or
                    range(bbox_ne_lat, {self.sw_lat}, {self.ne_lat})
                    or
                    (
                        bbox_sw_lat < {self.sw_lat}
                        and
                        bbox_ne_lat > {self.ne_lat}
                    )
                )
            """

        longitude_conditions = _generate_longitude_conditions()
        latitude_conditions = _generate_latitude_conditions()

        return {
            "yql": f"""
                select {self.fields}, locations from sources place
                where
                {longitude_conditions}
                and
                {latitude_conditions}
            """
        }
