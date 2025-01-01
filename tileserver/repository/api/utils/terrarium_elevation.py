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


def get_ground_resolution(lat: float, lng: float, maxzoom: int):
    """
    Calculate the ground resolution in metres per pixel for a given latitude, longitude, and zoom level.

    Args:
        lat (float): Latitude coordinate.
        lng (float): Longitude coordinate.
        maxzoom (int): Maximum zoom level.

    Returns:
        int: Ground resolution rounded to the nearest metre.
    """
    # Earth radius in meters
    earth_radius = 6378137

    # Convert lat/lng to resolution in meters per pixel at the given zoom level
    # Latitudinal resolution is constant, longitudinal resolution depends on the latitude
    pixel_resolution_latitude = (2 * math.pi * earth_radius) / (256 * 2 ** maxzoom)
    pixel_resolution_longitude = (math.cos(math.radians(lat)) * 2 * math.pi * earth_radius) / (256 * 2 ** maxzoom)

    # Calculate the precision based on the number of supplied decimal places, allowing for none
    precision_lat = 1 / (10 ** len(str(lat).split(".")[1])) if "." in str(lat) else 1
    precision_resolution_latitude = precision_lat * (math.pi * earth_radius / 180)
    precision_lng = 1 / (10 ** len(str(lng).split(".")[1])) if "." in str(lng) else 1
    precision_resolution_longitude = precision_lng * (math.pi * earth_radius / 180)

    # Round largest value up to the nearest metre
    return math.ceil(max(pixel_resolution_latitude, pixel_resolution_longitude, precision_resolution_latitude,
                         precision_resolution_longitude))


def get_elevation_data(lat: float, lng: float):
    """
    Retrieve elevation data for a given latitude and longitude.

    This function fetches tile data from a tileserver, calculates the elevation
    using Terrarium format, and retrieves metadata about the elevation.

    Args:
        lat (float): Latitude coordinate.
        lng (float): Longitude coordinate.

    Returns:
        dict: A dictionary containing elevation, ground resolution, metadata, and units.
    """
    try:
        logger.info(f"Fetching elevation for lat: {lat}, lng: {lng}")

        # Fetch the maxzoom from the tileserver
        terrarium_url = "http://tileserver-gl:8080/data/terrarium.json"
        metadata_response = requests.get(terrarium_url)
        metadata_response.raise_for_status()
        maxzoom = metadata_response.json().get("maxzoom", 10)
        logger.info(f"Maxzoom fetched from terrarium.json: {maxzoom}")

        # Calculate the tile indices
        x = int((lng + 180.0) / 360.0 * (2 ** maxzoom))
        y = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * (
                2 ** maxzoom))

        # Fetch the tile
        tile_url = f"http://tileserver-gl:8080/data/terrarium/{maxzoom}/{x}/{y}.png"
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
        ground_resolution = get_ground_resolution(lat, lng, maxzoom)

        # Read elevation resolution from Pickle file
        elevation_metadata = get_elevation_metadata(lat, lng, elevation)

        return {"elevation": elevation, "ground_resolution": ground_resolution, **elevation_metadata, "units": "metres"}
    except Exception as e:
        logger.info(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
