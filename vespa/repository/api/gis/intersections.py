# /gis/intersections.py

import json
import logging

from shapely.geometry.geo import shape

from .processor import vespa_bbox, get_valid_geom
from ..config import VespaClient

logger = logging.getLogger(__name__)


class IsoCodeResolver:
    """
    Resolves ISO 3166 Alpha-2 country codes for countries whose bounding boxes
    intersect with a given bounding box and whose geometries intersect with a given geometry.
    """

    def __init__(self, geometry=None, geom=None, bbox=None) -> None:
        """
        Initializes the resolver with a geometry and bounding box.

        Args:
            geometry (dict): The GeoJSON geometry to check against.
            bbox (dict): A bounding box dictionary with keys "bbox_sw_lat", "bbox_sw_lng", "bbox_ne_lat", "bbox_ne_lng".
        """

        # Validate and set geometry: geom is assumed to have been pre-validated
        if geom:
            self.geom = geom
        elif geometry:
            self.geom = get_valid_geom(geometry)

        # Derive bounding box if not provided
        self.bbox = bbox or (vespa_bbox(self.geom) if self.geom else None)
        self.vespa_client = VespaClient()

    def resolve(self) -> list:
        """
        Resolve ISO country codes by performing bounding box and geometry intersection checks.

        Returns:
            list: A sorted list of ISO country codes that intersect with the geometry.
        """
        if not self.geom or not self.bbox:
            logger.warning("Cannot resolve ISO codes: missing geometry or bounding box.")
            return []

        try:
            candidate_countries = BoxIntersect(self.bbox).box_intersect()

            ccodes = set()
            for country in candidate_countries:
                if 'code2' in country and country['code2'] != '-' and 'geometry' in country:
                    country_geom = shape(json.loads(country['geometry']))
                    if self.geom.intersects(country_geom):
                        ccodes.add(country['code2'])

            return sorted(list(ccodes))
        except Exception as e:
            logger.error(f"Error resolving ISO codes: {e}", exc_info=True)
            return []


class BoxIntersect:
    """
    Perform a spatial query in Vespa to find documents where the bounding box intersects
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
            fields (str, optional): Fields to query. Defaults to "code2, geometry".
        """
        self.min_lng = bbox.get("bbox_sw_lng", -180)
        self.min_lat = bbox.get("bbox_sw_lat", -90)
        self.max_lng = bbox.get("bbox_ne_lng", 180)
        self.max_lat = bbox.get("bbox_ne_lat", 90)
        self.schema = schema or "iso3166"
        self.fields = fields or "code2, geometry"

    def box_intersect(self) -> list:
        """
        Perform the Vespa query to find intersecting documents.

        Returns:
            list: A list of documents whose bounding boxes intersect with the provided bounding box.
        """
        try:
            with VespaClient.sync_context("feed") as sync_app:
                query = self._generate_bounding_box_query()
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
            if self.min_lng < self.max_lng:
                return f"""
                    (
                        range(bbox_sw_lng, {self.min_lng}, {self.max_lng})
                        or
                        range(bbox_ne_lng, {self.min_lng}, {self.max_lng})
                    )
                """
            else: # Crosses the antimeridian
                return f"""
                    (
                        range(bbox_sw_lng, -180, {self.max_lng})
                        or
                        range(bbox_sw_lng, {self.min_lng}, 180)
                        or
                        range(bbox_ne_lng, -180, {self.max_lng})
                        or
                        range(bbox_ne_lng, {self.min_lng}, 180)
                    )
                """

        def _generate_latitude_conditions() -> str:
            return f"""
                (
                    range(bbox_sw_lat, {self.min_lat}, {self.max_lat})
                    or
                    range(bbox_ne_lat, {self.min_lat}, {self.max_lat})
                )
            """

        longitude_conditions = _generate_longitude_conditions()
        latitude_conditions = _generate_latitude_conditions()

        return {
            "yql": f"""
                select {self.fields} from sources {self.schema}
                where
                {longitude_conditions}
                and
                {latitude_conditions}
            """
        }
