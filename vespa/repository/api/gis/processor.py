# /gis/processor.py
import json
import logging

from shapely.geometry.geo import shape
from shapely.io import to_geojson

from .intersections import GeometryIntersect
from .utils import get_valid_geom, vespa_bbox, geo_to_cartesian
from ..dates.dates import year_from_value

logger = logging.getLogger(__name__)


class GeometryProcessor:
    """
    A class to process GeoJSON geometries, validate them, compute properties such as area and bounding box,
    and resolve ISO country codes.
    """

    def __init__(self, geometry, values=None, errors=False) -> None:
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
        self.geom, self.geometry = get_valid_geom(
            geometry)  # Shapely geometry object, and valid GeoJSON geometry with non-standard fields preserved
        self.errors = errors

    def process(self) -> dict:
        """
        Processes the geometry and computes various properties such as area, bounding box, and ISO country codes.

        Returns:
            dict: A dictionary containing processed geometry properties, or:
                - {"error": "Invalid geometry"} if the input geometry is invalid.
                - {"error": "Empty geometry"} if the input geometry is empty.
                - None if `errors=False` and there are no valid properties to compute.
        """
        if not self.geom:
            # Invalidity and emptiness have been handled by get_valid_geom
            return {"error": "Invalid geometry"} if self.errors else None

        bbox = vespa_bbox(self.geom) if "bbox" in self.values or "ccodes" in self.values else {}
        convex_hull = self.geom.convex_hull if "convex_hull" in self.values else None
        iso_results = GeometryIntersect(geom=self.geom, bbox=bbox).resolve() if "ccodes" in self.values and bbox else {}
        # Remove "-" from the list of ISO codes if present
        iso_codes = [
            meta["ISO_A2"] for result in iso_results
            if "meta" in result and (meta := json.loads(result["meta"]))["ISO_A2"] != "-"
        ] or {}
        representative_point = (
            {"lat": (rp := self.geom.representative_point()).y, "lng": rp.x}
            if "representative_point" in self.values
            else None
        )
        cartesian = geo_to_cartesian(representative_point["lat"], representative_point["lng"]) if representative_point else None

        # Group geometries by matching temporal attributes (start and end)
        if self.geometry["type"] == "GeometryCollection":
            geometries = self.geometry["geometries"]
            grouped_geometries: dict = {}
            for geometry in geometries:
                start = year_from_value(geometry.get("start"))
                end = year_from_value(geometry.get("end"))
                key = (start, end)
                if key not in grouped_geometries:
                    grouped_geometries[key] = []
                grouped_geometries[key].append(geometry)

            # Pick the largest area and longest length from the geometry groups
            largest_area = 0
            longest_length = 0
            if "area" in self.values or "length" in self.values:
                for group in grouped_geometries.values():
                    geom = shape(
                        {"type": "GeometryCollection", "geometries": group})  # Convert GeoJSON to Shapely geometry
                    if geom:
                        area = geom.area
                        length = geom.length
                        if area > largest_area:
                            largest_area = area
                        if length > longest_length:
                            longest_length = length

            # Convert each group to a GeometryCollection JSON string within a location struct for indexing
            for key, group in grouped_geometries.items():
                grouped_geometries[key] = {
                    "geometry": json.dumps({"type": "GeometryCollection", "geometries": group}),
                    **({'year_start': key[0]} if key[0] else {}),
                    **({'year_end': key[1]} if key[1] else {}),
                }

            locations = list(grouped_geometries.values())

        else:
            locations = [{"geometry": json.dumps(self.geometry)}]
            largest_area = self.geom.area if "area" in self.values else None
            longest_length = self.geom.length if "length" in self.values else None

        return {
            **({"area": largest_area} if largest_area else {}),  # Omitted if zero or None
            **(bbox if bbox else {}),
            **({"convex_hull": to_geojson(convex_hull)} if convex_hull else {}),
            **({"locations": locations} if locations else {}),
            **({"ccodes": iso_codes} if iso_codes else {}),
            **({"length": longest_length} if longest_length else {}),  # Omitted if zero or None
            **({"representative_point": representative_point} if representative_point else {}), # Stored not as GeoJSON but as Vespa `position` type
            **({"cartesian": cartesian} if cartesian else {}),
        }
