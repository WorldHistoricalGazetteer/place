import logging
import math
import os
import pickle
from contextlib import asynccontextmanager
from io import BytesIO

import requests
import rtree
from PIL import Image
from fastapi import HTTPException, FastAPI
from shapely.geometry import shape

# Configure logging
logger = logging.getLogger(__name__)

bounds_map = {}
geometry_map = {}
properties_map = {}
descriptions_map = {}
idx = rtree.index.Index()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.

    This function performs necessary startup tasks and yields control
    to the application during its lifecycle.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    init_elevation_data()
    yield


def load_data(file_path: str):
    """
    Load data from a pickle file.

    Args:
        file_path (str): Path to the pickle file.

    Returns:
        Any: Data loaded from the pickle file, or None if an error occurs.
    """
    try:
        with open(file_path, "rb") as f:
            data = pickle.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading pickle file: {e}")
        return None


def init_elevation_data():
    """
    Initialise Terrarium elevation metadata by loading it from a pickle file.

    The pickle file is generated from geojson data available
    at https://github.com/tilezen/joerd/blob/master/docs/data-sources.md

    This function also constructs an RTree index using the loaded data and
    populates global maps for bounds, geometry, properties, and descriptions.
    """
    pickle_file_path = os.path.join(os.path.dirname(__file__), 'data', 'terrarium-data.pkl')
    data = load_data(pickle_file_path)
    if data:
        logger.info("Loaded data from pickle file")
        global bounds_map, geometry_map, properties_map, descriptions_map, idx
        bounds_map = data['bounds']
        geometry_map = data['geometry']
        properties_map = data['properties']
        descriptions_map = data['descriptions']
        logger.info(f"Descriptions: {descriptions_map}")

        # Build the RTree index
        for i, bounds in bounds_map.items():
            idx.insert(i, bounds)
        logger.info("Built RTree index")
    else:
        logger.error("Failed to load data or build index")


def get_elevation_metadata(lat: float, lng: float, elevation: float):
    """
    Retrieve metadata about the elevation for a given latitude and longitude.

    Args:
        lat (float): Latitude coordinate.
        lng (float): Longitude coordinate.
        elevation (float): Elevation value.

    Returns:
        dict: Elevation metadata including resolution and source.
    """
    if len(bounds_map) == 0:
        logger.info("No data loaded from pickle file")
        return {"elevation_resolution": None, "elevation_source": None}

    try:
        logger.info(f"Finding elevation metadata for lat: {lat}, lng: {lng}")

        # Query the RTree index with the latitude and longitude
        result = list(idx.intersection((lng - 0.0001, lat - 0.0001, lng + 0.0001, lat + 0.0001)))

        if not result:
            logger.info("No elevation metadata found")
            logger.info(f"idx type: {type(idx)}")
            return {"elevation_resolution": None,
                    "elevation_source": None}

        # Refine results by checking intersections with geometry_map
        if len(result) > 1:
            result = [i for i in result if
                      geometry_map[i].contains(shape({'type': 'Point', 'coordinates': [lng, lat]}))]

        # Select the feature with the minimum resolution
        feature_id = min(result, key=lambda x: properties_map[x]['resolution'])
        feature = properties_map[feature_id]
        source = feature['source']
        description = descriptions_map.get(source, "No description available")

        # Round feature resolution to nearest 0.1 metres
        feature['resolution'] = round(feature['resolution'], 1)

        # Round elevation appropriately
        elevation = round(round(elevation / feature['resolution']) * feature['resolution'])

        return {
            "elevation": elevation,
            "elevation_resolution": feature['resolution'],
            "elevation_source": description
        }
    except Exception as e:
        logger.error(f"Error retrieving elevation: {e}")
        return {"elevation_resolution": None, "elevation_source": None}


def get_ground_resolution(lat: float, max_zoom: int, lat_string: str, lng_string: str):
    """
    Calculate the ground resolution in metres per pixel for a given latitude, longitude, and zoom level.

    Args:
        lat (float): Latitude coordinate.
        max_zoom (int): Maximum zoom level.
        lat_string (str): Latitude coordinate as a string.
        lng_string (str): Longitude coordinate as a string.

    Returns:
        int: Ground resolution rounded to the nearest metre.
    """
    # Earth radius in meters
    earth_radius = 6378137

    # Convert lat/lng to resolution in meters per pixel at the given zoom level
    # Latitudinal resolution is constant, longitudinal resolution depends on the latitude
    pixel_resolution_latitude = (2 * math.pi * earth_radius) / (256 * 2 ** max_zoom)
    pixel_resolution_longitude = (math.cos(math.radians(lat)) * 2 * math.pi * earth_radius) / (256 * 2 ** max_zoom)

    # Calculate the precision based on the number of supplied decimal places, allowing for none
    precision_lat = 1 / (10 ** len(lat_string.split(".")[1])) if "." in lat_string else 1
    precision_resolution_latitude = precision_lat * (math.pi * earth_radius / 180)
    precision_lng = 1 / (10 ** len(lng_string.split(".")[1])) if "." in lng_string else 1
    precision_resolution_longitude = precision_lng * (math.pi * earth_radius / 180)

    # Multiply largest value by square root of 2 to get diagonal resolution
    largest_value = max(pixel_resolution_latitude, pixel_resolution_longitude, precision_resolution_latitude,
                        precision_resolution_longitude)
    diagonal_resolution = largest_value * math.sqrt(2)

    # Round up to the nearest metre
    return math.ceil(diagonal_resolution)


def get_elevation_data(lat_string: str, lng_string: str):
    """
    Retrieve elevation data for a given latitude and longitude.

    This function fetches tile data from a tileserver, calculates the elevation
    using Terrarium format, and retrieves metadata about the elevation.

    Args:
        lat_string (str): Latitude coordinate.
        lng_string (str): Longitude coordinate.

    Returns:
        dict: A dictionary containing elevation, ground resolution, metadata, and units.
    """
    try:
        logger.info(f"Fetching elevation for lat: {lat_string}, lng: {lng_string}")

        # Convert lat/lng to float
        lat = float(lat_string)
        lng = float(lng_string)

        # Fetch the max_zoom from the tileserver
        terrarium_url = "http://tileserver-gl:8080/data/terrarium.json"
        metadata_response = requests.get(terrarium_url)
        metadata_response.raise_for_status()
        max_zoom = metadata_response.json().get("max_zoom", 10)
        logger.info(f"max_zoom fetched from terrarium.json: {max_zoom}")

        # Calculate the tile indices
        x = int((lng + 180.0) / 360.0 * (2 ** max_zoom))
        y = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * (
                2 ** max_zoom))

        # Fetch the tile
        tile_url = f"http://tileserver-gl:8080/data/terrarium/{max_zoom}/{x}/{y}.png"
        logger.info(f"Fetching tile from {tile_url}")
        response = requests.get(tile_url)
        response.raise_for_status()

        # Decode the image
        tile_image = Image.open(BytesIO(response.content))
        pixel_x = int((lng + 180.0) % 360.0 * (tile_image.width / 360.0))
        pixel_y = int((1.0 - (lat + 90.0) / 180.0) * tile_image.height)
        logger.info(f"Pixel position: x={pixel_x}, y={pixel_y}")

        # Get RGB values
        r, g, b = tile_image.getpixel((pixel_x, pixel_y))

        # Calculate elevation based on Terrarium format
        elevation = (r * 256 + g + b / 256) - 32768
        logger.info(f"Elevation: {elevation} metres")

        # Calculate ground resolution
        ground_resolution = get_ground_resolution(lat, max_zoom, lat_string, lng_string)

        # Read elevation resolution from Pickle file
        elevation_metadata = get_elevation_metadata(lat, lng, elevation)

        # Build text representations
        elevation_text = f"{elevation_metadata['elevation']} {chr(177)}{elevation_metadata['elevation_resolution']} metres"
        ground_resolution_radius = f"{ground_resolution}m" if ground_resolution < 1000 else f"{round(ground_resolution / 1000, 1)}km"
        lat_text = f"{lat_string.lstrip('-')}{chr(176)}{'S' if lat < 0 else 'N'}"
        lng_text = f"{lng_string.lstrip('-')}{chr(176)}{'W' if lng < 0 else 'E'}"
        ground_resolution_text = f"within a radius of {ground_resolution_radius} of {lat_text} {lng_text}"

        return {"elevation_text": elevation_text, "ground_resolution_text": ground_resolution_text,
                "ground_resolution_note": "Calculation is dependent on the latitude, zoom level, and decimal-precision of the coordinates.",
                "elevation": elevation, "ground_resolution": ground_resolution, **elevation_metadata,
                "source_note": f"Elevation data collated from various sources by Mapzen/Terrarium. WHG currently employs data up to zoom level {max_zoom}.",
                "units": "metres"}
    except Exception as e:
        logger.info(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
