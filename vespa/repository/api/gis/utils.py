# /gis/utils.py


def float_geometry(geometry, has_Decimal=False):
    if not has_Decimal or not geometry or 'type' not in geometry or 'coordinates' not in geometry:
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


def isocodes(geometries, has_Decimal=False):
    # Collect ISO codes from countries intersecting with the provided geometries

    ccodes = set()
    for geom in geometries:
        geometry = geom.get('geometry', geom)

        if geometry:
            parsed_geometry = float_geometry(geometry, has_Decimal)
            logger.debug(f"Parsed geometry: {parsed_geometry}")
            geos_geometry = GEOSGeometry(json.dumps(parsed_geometry))

            # Query the Country model for intersections with the provided geometry
            qs = Country.objects.filter(mpoly__intersects=geos_geometry)
            ccodes.update([country.iso for country in qs])

    return sorted(ccodes)