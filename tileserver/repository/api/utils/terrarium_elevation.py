import logging
import math
from io import BytesIO

import requests
import rtree
from PIL import Image
from fastapi import HTTPException

from ..config import host_mapping, descriptions_map

logger = logging.getLogger(__name__)

bounds_map = {}
geometry_map = {}
properties_map = {}
idx = rtree.index.Index()


def get_elevation_metadata(lat: float, lng: float, elevation: float) -> dict:
    """
    Retrieve metadata about the elevation for a given latitude and longitude.

    Args:
        lat (float): Latitude coordinate.
        lng (float): Longitude coordinate.
        elevation (float): Elevation value.

    Returns:
        dict: Elevation metadata including resolution, source, and elevation.
    """
    logger.info(f"Finding elevation metadata for lat: {lat}, lng: {lng}")

    terrarium_url = f"http://{host_mapping['feed']}/terrarium/{lat}/{lng}"

    try:
        response = requests.get(terrarium_url)
        response.raise_for_status()

        response_data = response.json()
        source = response_data.get("source")
        result = {
            "elevation_resolution": response_data.get("resolution"),
            "elevation_source": descriptions_map.get(source, 'No description available') if source else None,
        }

        if result["elevation_resolution"] and result["elevation_source"]:
            result["elevation"] = elevation
        else:
            logger.info("Incomplete elevation metadata found")

        return result

    except requests.RequestException as e:
        logger.error(f"HTTP error while retrieving elevation metadata: {e}")
    except ValueError as e:  # For JSON decoding errors
        logger.error(f"Error parsing JSON response: {e}")
    except Exception as e:
        logger.error(f"Unexpected error retrieving elevation metadata: {e}")

    return {
        "elevation_resolution": None,
        "elevation_source": None,
    }


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

        # Check if lat/lng are within bounds
        if lat < -90 or lat > 90 or lng < -180 or lng > 180:
            return {"status": "error", "message": "Invalid latitude or longitude"}

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
        elevation_text = f"{elevation_metadata['elevation']} ±{elevation_metadata['elevation_resolution']} metres"
        ground_resolution_radius = f"{ground_resolution}m" if ground_resolution < 1000 else f"{round(ground_resolution / 1000, 1)}km"
        lat_text = f"{lat_string.lstrip('-')}°{'S' if lat < 0 else 'N'}"
        lng_text = f"{lng_string.lstrip('-')}°{'W' if lng < 0 else 'E'}"
        ground_resolution_text = f"within a radius of {ground_resolution_radius} of {lat_text} {lng_text}"

        return {"elevation_text": elevation_text, "ground_resolution_text": ground_resolution_text,
                "ground_resolution_note": f"Calculation is dependent on the latitude, maximum data zoom level (currently {max_zoom}), and decimal-precision of the coordinates.",
                "elevation": elevation, "ground_resolution": ground_resolution, **elevation_metadata,
                "source_note": f"Elevation data collated from various sources by Mapzen/Terrarium, and self-hosted by WHG.",
                "units": "metres", "status": "success"}
    except Exception as e:
        logger.info(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
