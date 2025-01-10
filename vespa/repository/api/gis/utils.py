# /gis/utils.py
from shapely.geometry.geo import shape
from shapely.geometry.point import Point
from shapely.validation import explain_validity


def bbox(geometry, tensor=True, errors=True):
    """
    Calculate the bounding box of a geometry and return it (by default) as a tensor(x[2],y[2]).

    :param geometry: A GeoJSON geometry object.
    :param tensor: Whether to return the bounding box as a tensor(x[2],y[2]) or a list(xmin,ymin,xmax,ymax).
    :return: A dictionary representing the tensor(x[2],y[2]) format for Vespa, or a list(xmin,ymin,xmax,ymax), or an error message.
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
        x, y = geom.x, geom.y
        return {
            "x": [x, x],
            "y": [y, y]
        }

    minx, miny, maxx, maxy = geom.bounds

    # Convert to float
    minx, miny, maxx, maxy = float(minx), float(miny), float(maxx), float(maxy)

    # Convert to tensor format
    return {
        "x": [minx, maxx],
        "y": [miny, maxy]
    } if tensor else [minx, miny, maxx, maxy]


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


def isocodes(geometries, has_decimal=False):
    # Collect ISO codes from countries intersecting with the provided geometries

    # TODO: Convert this from PostGIS to Vespa + Shapely

    # ccodes = set()
    # for geom in geometries:
    #     geometry = geom.get('geometry', geom)
    #
    #     if geometry:
    #         parsed_geometry = float_geometry(geometry, has_decimal)
    #         logger.debug(f"Parsed geometry: {parsed_geometry}")
    #         geos_geometry = GEOSGeometry(json.dumps(parsed_geometry))
    #
    #         # Query the Country model for intersections with the provided geometry
    #         qs = Country.objects.filter(mpoly__intersects=geos_geometry)
    #         ccodes.update([country.iso for country in qs])
    #
    # return sorted(ccodes)

    return {}
