# /gis/utils.py
import json
import math

from shapely.geometry.geo import shape, box
from shapely.geometry.point import Point
from shapely.validation import explain_validity

from ..config import VespaClient


def bbox(geometry, positions=True, errors=True):
    """
    Calculate the bounding box of a geometry and return it (by default) as a positions [{lat, lng}, {lat, lng}] format for Vespa.

    :param geometry: A GeoJSON geometry object.
    :param positions: Whether to return the bounding box as positions [{lat, lng}, {lat, lng}] or a list(xmin,ymin,xmax,ymax).
    :param errors: Whether to return an error message if the geometry is invalid.
    :return: A dictionary representing the positions [{lat, lng}, {lat, lng}] format for Vespa, or a list(xmin,ymin,xmax,ymax), or an error message.
    """
    if not geometry or 'type' not in geometry or 'coordinates' not in geometry:
        return {"error": "Invalid geometry"} if errors else None

    try:
        geom = shape(geometry)
    except Exception as e:
        return {"error": f"Invalid geometry: {e}"} if errors else None

    if not geom.is_valid:
        return {"error": f"Invalid geometry: {explain_validity(geom)}"} if errors else None

    # Short-circuit for Point geometries
    if isinstance(geom, Point):
        lng, lat = float(geom.x), float(geom.y)
        if any(math.isnan(v) or math.isinf(v) for v in (lng, lat)):
            return {"error": "Invalid geometry (NaN or Infinity)"} if errors else None
        else:
            return { # lat & lng are transposed
                "sw": {"lat": lat, "lng": lng},
                "ne": {"lat": lat, "lng": lng}
            } if positions else [lng, lat, lng, lat]

    min_lng, min_lat, max_lng, max_lat = geom.bounds

    # return None if any value is NaN or Infinity
    if any(math.isnan(v) or math.isinf(v) for v in (min_lng, min_lat, max_lng, max_lat)):
        return {"error": "Invalid geometry (NaN or Infinity)"} if errors else None

    # Convert to float
    min_lng, min_lat, max_lng, max_lat = float(min_lng), float(min_lat), float(max_lng), float(max_lat)

    # Convert to positions format
    return { # lat & lng are transposed
        "sw": {"lat": min_lat, "lng": min_lng},
        "ne": {"lat": max_lat, "lng": max_lng}
    } if positions else [min_lng, min_lat, max_lng, max_lat]


def float_geometry(geometry, has_decimal=False):
    if not has_decimal or not geometry or 'type' not in geometry or 'coordinates' not in geometry:
        return geometry

    geom_type = geometry.get('type')
    coordinates = geometry.get('coordinates')

    # Handle various geometry types
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


def box_intersect(test_box, schema_name, schema_fields="*", schema_box="bbox"):
    """
    Perform a spatial query in Vespa to find documents in the specified schema 
    where the specified field (default: `bounding_box`) intersects with the given bounding box.

    :param test_box: A list representing the SW and NE corners of a bounding box in Vespa `position` format,
                         e.g., [{lat, lng}, {lat, lng}].
    :param schema_name: The name of the Vespa schema to query.
    :param schema_fields: A comma-separated string of field names to retrieve in the query result (default: "*", which retrieves all fields).
    :param schema_box: The field name in the schema (default: "bounding_box") to check for spatial intersection with the bounding box.
    :return: A list of documents from Vespa that match the spatial intersection condition, or an empty list if no matches are found.
    :raises ValueError: If there is an error during the Vespa query or processing.
    """
    try:
        with VespaClient.sync_context("feed") as sync_app:

            if test_box["sw"]["lng"] > test_box["ne"]["lng"]:
                query = {
                    "yql": f"""
                                select {schema_fields} 
                                from sources {schema_name} 
                                where 
                                (
                                    range(sw.lng, {test_box["sw"]["lng"]}, {test_box["ne"]["lng"]}) 
                                    or 
                                    range({schema_box}["ne"]["lng"], {test_box["sw"]["lng"]}, {test_box["ne"]["lng"]})
                                ) 
                                and
                                (
                                    range(sw.lat, {test_box["sw"]["lat"]}, {test_box["ne"]["lat"]}) 
                                    or 
                                    range({schema_box}["ne"]["lat"], {test_box["sw"]["lat"]}, {test_box["ne"]["lat"]})
                                )
                            """
                }
            else:
                query = {
                    "yql": f"""
                                select {schema_fields} 
                                from sources {schema_name} 
                                where 
                                (
                                    range(sw.lng, -180, {test_box["ne"]["lng"]}) 
                                    or 
                                    range(sw.lng, {test_box["sw"]["lng"]}, 180) 
                                    or 
                                    range({schema_box}["ne"]["lng"], -180, {test_box["ne"]["lng"]}) 
                                    or 
                                    range({schema_box}["ne"]["lng"], {test_box["sw"]["lng"]}, 180)
                                ) 
                                and
                                (
                                    range(sw.lat, {test_box["sw"]["lat"]}, {test_box["ne"]["lat"]}) 
                                    or 
                                    range({schema_box}["ne"]["lat"], {test_box["sw"]["lat"]}, {test_box["ne"]["lat"]})
                                )
                            """
                }

            # Execute the Vespa query and handle the response
            response = sync_app.query(query)
            if "error" in response:
                raise ValueError(f"Error during Vespa query: {response['error']}")

            # Return the documents matching the spatial intersection condition
            return response.get("hits", [])

    except Exception as e:
        raise ValueError(f"Error during Vespa query: {str(e)}")


def isocodes(bbox, geometry):
    """
    Determine the ISO 3166 Alpha-2 country codes for countries whose bounding boxes
    intersect with the provided bounding box and whose geometries intersect
    with the provided geometry.

    :param bbox: A dictionary representing the SW and NE corners of the bounding box in Vespa `position` format,
                 e.g., [{lat, lng}, {lat, lng}].
    :param geometry: A GeoJSON geometry object used to refine the intersection
                     check beyond the bounding box level.
    :return: A sorted list of ISO 3166 Alpha-2 country codes for intersecting countries.
    """
    # Use Search API to query the iso3166 schema for countries whose bounding boxes intersect with that provided
    candidate_countries = box_intersect(bbox, "iso3166", "code2,geometry")

    # Use Shapely to check for intersections with the provided geometry
    geom = shape(geometry)
    ccodes = set()
    for country in candidate_countries:
        ccodes.add(country['code2'])


        # country_geom = shape(country['geometry'])
        # if geom.intersects(country_geom):
        #     ccodes.add(country['code2'])

    return sorted(list(ccodes))
