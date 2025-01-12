# /gis/processor.py
import json
import logging
import math

from shapely.geometry.geo import shape
from shapely.io import to_geojson
from shapely.validation import explain_validity

from ..config import VespaClient

logger = logging.getLogger(__name__)


class GeometryProcessor:
    """
    A class that processes GeoJSON geometries, providing various useful properties
    and performing operations such as bounding box calculation, geometry validation,
    and intersection checks with countries.

    Attributes:
        geometry (dict): The GeoJSON geometry to be processed.
        values (list): A list of properties to compute.
        errors (bool): If True, errors will be returned as messages.
        geom (shapely.geometry.base.BaseGeometry): The Shapely geometry object derived from the GeoJSON.
    """

    def __init__(self, geometry, values=None, errors=False):
        """
        Initializes the GeometryProcessor with a given geometry, optional attributes to compute,
        and an error-handling option.

        Args:
            geometry (dict): The GeoJSON geometry to be processed.
            values (list, optional): A list of properties to compute. Defaults to ["area", "bbox",
                                      "ccodes", "convex_hull", "geometry", "length", "representative_point"]
                                      if not provided.
            errors (bool): If True, errors will be returned as messages. Defaults to False.
        """
        self.values = values or ["area", "bbox", "ccodes", "convex_hull", "geometry", "length", "representative_point"]
        self.geometry = geometry  # GeoJSON geometry
        self.geom = None  # Shapely geometry object
        self.errors = errors

        if self.is_valid_geometry():
            self.geom = shape(geometry)
        else:
            self.geom = None

    def is_valid_geometry(self):
        """
        Check if the provided geometry is valid.

        Returns:
            bool: True if the geometry is valid, False otherwise.
        """
        if not self.geometry or 'type' not in self.geometry or 'coordinates' not in self.geometry:
            return False
        try:
            shape(self.geometry)
        except Exception:
            return False
        return True

    def process(self):
        """
        Processes the geometry and returns a dictionary with various properties
        calculated from the geometry, such as area, bounding box, ISO country codes,
        and geometry details.

        Returns:
            dict: A dictionary containing processed geometry properties or an error message.
        """
        if not self.geom:
            return {"error": "Invalid geometry"} if self.errors else None

        if not self.geom.is_valid:
            return {"error": f"Invalid geometry: {explain_validity(self.geom)}"} if self.errors else None

        if self.geom.is_empty:
            return {"error": "Empty geometry"} if self.errors else None

        # If requested, cache values for performance efficiency
        area = self.geom.area if "area" in self.values else None
        bbox_codes = self._bbox_ccodes() if "bbox" in self.values else {}
        convex_hull = self.geom.convex_hull if "convex_hull" in self.values else None
        float_geometry = self._float_geometry() if "geometry" in self.values else None
        length = self.geom.length if "length" in self.values else None
        representative_point = self.geom.representative_point() if "representative_point" in self.values else None

        return {
            **({"area": area} if area else {}),
            **bbox_codes,
            **({"convex_hull": to_geojson(convex_hull)} if convex_hull else {}),
            **({"geometry": json.dumps(float_geometry)} if float_geometry else {}),
            **({"length": length} if length else {}),
            **({"representative_point": to_geojson(representative_point)} if representative_point else {}),
        }

    def _bbox_ccodes(self):
        """
        Calculate the bounding box of a geometry and return it in Vespa-friendly format.
        It also checks for ISO country codes that intersect with the geometry's bounding box.

        Returns:
            dict: A dictionary containing bounding box coordinates and the country codes (ccodes)
                  that intersect with the geometry.
        """
        min_lng, min_lat, max_lng, max_lat = self.geom.bounds

        if any(math.isnan(v) or math.isinf(v) for v in (min_lng, min_lat, max_lng, max_lat)):
            return {"bbox_error": "Invalid geometry (NaN or Infinity)"} if self.errors else {}

        return {
            "bbox_sw_lat": min_lat,
            "bbox_sw_lng": min_lng,
            "bbox_ne_lat": max_lat,
            "bbox_ne_lng": max_lng,
            **({"ccodes": self._isocodes(min_lng, min_lat, max_lng, max_lat)} if "ccodes" in self.values else {})
        }

    def _float_geometry(self):
        """
        Convert the geometry's coordinates to floats to enable serialization.

        Returns:
            dict: A dictionary containing the geometry type and its coordinates with all values as floats.
        """
        if not self.geometry or 'type' not in self.geometry or 'coordinates' not in self.geometry:
            return self.geometry

        geom_type = self.geometry.get('type')
        coordinates = self.geometry.get('coordinates')

        if geom_type in ['Point']:
            coordinates = [float(coord) for coord in coordinates]
        elif geom_type in ['LineString']:
            coordinates = [[float(coord) for coord in point] for point in coordinates]
        elif geom_type in ['Polygon']:
            coordinates = [[[float(coord) for coord in point] for point in ring] for ring in coordinates]
        elif geom_type in ['MultiPoint']:
            coordinates = [[float(coord) for coord in point] for point in coordinates]
        elif geom_type == 'MultiLineString':
            coordinates = [[[float(coord) for coord in point] for point in line] for line in coordinates]
        elif geom_type == 'MultiPolygon':
            coordinates = [[[[float(coord) for coord in point] for point in ring] for ring in polygon] for polygon in
                           coordinates]

        return {
            "type": geom_type,
            "coordinates": coordinates
        }

    def _isocodes(self, min_lng, min_lat, max_lng, max_lat):
        """
        Determine the ISO 3166 Alpha-2 country codes for countries whose bounding boxes
        intersect with the provided bounding box and whose geometries intersect
        with the provided geometry.

        Args:
            min_lng (float): The minimum longitude of the geometry's bounding box.
            min_lat (float): The minimum latitude of the geometry's bounding box.
            max_lng (float): The maximum longitude of the geometry's bounding box.
            max_lat (float): The maximum latitude of the geometry's bounding box.

        Returns:
            list: A sorted list of ISO country codes that intersect with the geometry.
        """
        try:
            candidate_countries = self._box_intersect(min_lng, min_lat, max_lng, max_lat)
            geom = shape(self.geometry)
            ccodes = set()
            for country in candidate_countries:
                if 'code2' in country and country['code2'] != '-' and 'geometry' in country:
                    country_geom = shape(json.loads(country['geometry']))
                    if geom.intersects(country_geom):
                        ccodes.add(country['code2'])

            logger.info(f"ISO codes for bounding box: {ccodes}")
            return sorted(list(ccodes))

        except Exception as e:
            logger.error(f"Error determining ISO codes: {e}", exc_info=True)
            return []

    def _box_intersect(self, min_lng, min_lat, max_lng, max_lat):
        """
        Perform a spatial query in Vespa to find documents where the bounding box intersects
        with the provided bounding box.

        Args:
            min_lng (float): The minimum longitude of the bounding box.
            min_lat (float): The minimum latitude of the bounding box.
            max_lng (float): The maximum longitude of the bounding box.
            max_lat (float): The maximum latitude of the bounding box.

        Returns:
            list: A list of documents (children) whose bounding boxes intersect with the given bounding box.
        """
        try:
            with VespaClient.sync_context("feed") as sync_app:
                query = self._generate_bounding_box_query(min_lng, min_lat, max_lng, max_lat)
                response = sync_app.query(query).json
                if "error" in response:
                    raise ValueError(f"Error during Vespa query: {response['error']}")
                return [child.get("fields", {}) for child in response.get("root", {}).get("children", [])]

        except Exception as e:
            raise ValueError(f"Error during Vespa query: {str(e)}")

    def _generate_bounding_box_query(self, min_lng, min_lat, max_lng, max_lat):
        """
        Generate the YQL query to check country bounding boxes for spatial intersections with a bounding box.

        Args:
            min_lng (float): The minimum longitude of the bounding box.
            min_lat (float): The minimum latitude of the bounding box.
            max_lng (float): The maximum longitude of the bounding box.
            max_lat (float): The maximum latitude of the bounding box.

        Returns:
            dict: The YQL query for the bounding box intersection.
        """
        if min_lng > max_lng:
            return {
                "yql": f"""
                            select "code2,geometry" from sources iso3166
                            where
                            (
                                range(bbox_sw_lng, {min_lng}, {max_lng})
                                or
                                range(bbox_ne_lng, {min_lng}, {max_lng})
                            )
                            and
                            (
                                range(bbox_sw_lat, {min_lat}, {max_lat})
                                or
                                range(bbox_ne_lat, {min_lat}, {max_lat})
                            )
                        """
            }
        else:
            return {
                "yql": f"""
                            select "code2,geometry" from sources iso3166
                            where
                            (
                                range(bbox_sw_lng, -180, {max_lng})
                                or
                                range(bbox_sw_lng, {min_lng}, 180)
                                or
                                range(bbox_ne_lng, -180, {max_lng})
                                or
                                range(bbox_ne_lng, {min_lng}, 180)
                            )
                            and
                            (
                                range(bbox_sw_lat, {min_lat}, {max_lat})
                                or
                                range("bbox_ne_lat", {min_lat}, {max_lat})
                            )
                        """
            }
