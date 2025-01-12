# /gis/processor.py

import json
import logging

from shapely.io import to_geojson
from shapely.validation import explain_validity

from .intersections import IsoCodeResolver
from .utils import get_valid_geom, vespa_bbox

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
        self.geometry = geometry  # GeoJSON geometry
        self.geom = get_valid_geom(geometry)
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
            return {"error": "Invalid geometry"} if self.errors else None

        if not self.geom.is_valid:
            return {"error": f"Invalid geometry: {explain_validity(self.geom)}"} if self.errors else None

        if self.geom.is_empty:
            return {"error": "Empty geometry"} if self.errors else None

        # If requested, cache values for performance efficiency
        area = self.geom.area if "area" in self.values else None
        bbox = vespa_bbox(self.geom) if "bbox" in self.values or "ccodes" in self.values else {}
        convex_hull = self.geom.convex_hull if "convex_hull" in self.values else None
        float_geometry = self._float_geometry() if "geometry" in self.values else None
        iso_codes = IsoCodeResolver(geom=self.geom, bbox=bbox).resolve() if "ccodes" in self.values and bbox else {}
        length = self.geom.length if "length" in self.values else None
        representative_point = self.geom.representative_point() if "representative_point" in self.values else None

        return {
            **({"area": area} if area else {}),
            **(bbox if bbox else {}),
            **({"convex_hull": to_geojson(convex_hull)} if convex_hull else {}),
            **({"geometry": json.dumps(float_geometry)} if float_geometry else {}),
            **({"ccodes": iso_codes} if iso_codes else {}),
            **({"length": length} if length else {}),
            **({"representative_point": to_geojson(representative_point)} if representative_point else {}),
        }

    def _float_geometry(self) -> dict:
        """
        Convert the geometry's coordinates to floats to enable serialization.

        Returns:
            dict: A dictionary containing the geometry type and its coordinates with all values as floats.
        """
        if not self.geometry or 'type' not in self.geometry or 'coordinates' not in self.geometry:
            return self.geometry

        def convert_coordinates(coords) -> list:
            """
            Recursively convert all coordinate values to float.

            Args:
                coords (list): A list of coordinates or nested lists.

            Returns:
                list: A list with all coordinate values converted to float.
            """
            if isinstance(coords[0], (list, tuple)):  # Nested coordinates
                return [convert_coordinates(c) for c in coords]
            return [float(coord) for coord in coords]

        geom_type = self.geometry['type']
        coordinates = self.geometry['coordinates']

        return {
            "type": geom_type,
            "coordinates": convert_coordinates(coordinates),
        }
