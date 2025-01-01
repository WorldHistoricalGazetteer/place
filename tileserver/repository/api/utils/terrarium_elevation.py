import logging
import math
import os
import pickle
from io import BytesIO

import requests
from PIL import Image
from fastapi import HTTPException

# Configure logging
logger = logging.getLogger(__name__)


# Load the pickle data
def load_data(file_path: str):
    try:
        with open(file_path, "rb") as f:
            data = pickle.load(f)
        return data
    except Exception as e:
        logger.error(f"Error loading pickle file: {e}")
        return None


def get_elevation_metadata(lat: float, lng: float):
    pickle_file_path = os.path.join(os.path.dirname(__file__), 'data', 'terrarium-data.pkl')
    data = load_data(pickle_file_path)
    if data:
        idx = data['index']
        properties_map = data['properties']
        descriptions_map = data['descriptions']
    else:
        logger.info("No data loaded from pickle file")
        idx = properties_map = descriptions_map = {}

    try:
        logger.info(f"Fetching elevation metadata for lat: {lat}, lng: {lng}")
        logger.info(f"Index length: {len(properties_map)}")
        logger.info(f"Descriptions: {descriptions_map}")

        # Query the RTree index with the latitude and longitude
        result = list(idx.intersection((lng - 0.0001, lat - 0.0001, lng + 0.0001, lat + 0.0001)))

        if not result:
            logger.info("No elevation metadata found")
            logger.info(f"idx type: {type(idx)}")
            # Log intersection with a larger area
            result = list(idx.intersection((10, 10, 90, 90)))
            logger.info(f"Intersection with larger area: {result}")
            return {"elevation_resolution": None,
                    "elevation_source": None}

        # Select the feature with the minimum resolution (this can be enhanced)
        feature_id = min(result, key=lambda x: properties_map[x]['resolution'])
        feature = properties_map[feature_id]
        source = feature['source']
        description = descriptions_map.get(source, "No description available")

        return {
            "elevation_resolution": feature['resolution'],
            "elevation_source": description
        }
    except Exception as e:
        logger.error(f"Error retrieving elevation: {e}")
        return {"elevation_resolution": None, "elevation_source": None}


def get_ground_resolution(lat: float, lng: float, maxzoom: int):
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
    return math.ceil(max(pixel_resolution_latitude, pixel_resolution_longitude, precision_resolution_latitude, precision_resolution_longitude))


def get_elevation_data(lat: float, lng: float):
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
        elevation_metadata = get_elevation_metadata(lat, lng)

        return {"elevation": elevation, "ground_resolution": ground_resolution, **elevation_metadata}
    except Exception as e:
        logger.info(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
