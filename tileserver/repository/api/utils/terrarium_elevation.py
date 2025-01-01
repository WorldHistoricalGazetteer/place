import logging
import math
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
    data = load_data("./utils/data/terrarium-data.pkl")
    if data:
        idx = data['index']
        properties_map = data['properties']
        descriptions_map = data['descriptions']
    else:
        idx = properties_map = descriptions_map = {}

    try:
        # Query the RTree index with the latitude and longitude
        result = list(idx.intersection((lng - 0.0001, lat - 0.0001, lng + 0.0001, lat + 0.0001)))

        if not result:
            return {"elevation": None, "ground_resolution": None, "elevation_resolution": None,
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

        # Calculate ground resolution
        # TODO: Account for input resolution implicit in decimal places provided
        ground_resolution = (math.cos(math.radians(lat)) * 2 * math.pi * 6378137) / (
                    256 * 2 ** maxzoom)  # metres per pixel

        # Read elevation resolution from Pickle file
        elevation_metadata = get_elevation_metadata(lat, lng)

        return {"elevation": elevation, "ground_resolution": ground_resolution, **elevation_metadata}
    except Exception as e:
        logger.error(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
