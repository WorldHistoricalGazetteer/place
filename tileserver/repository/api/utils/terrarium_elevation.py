import json
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

descriptions_map = {
    "austria": "Digital elevation model with 10-metre resolution over Austria, provided by data.gv.at.",
    "etopo1": "Global ocean bathymetry model with a 1 arc-minute resolution, covering the world’s oceans.",
    "eudem": "EU-DEM offers 30-metre resolution in most European countries, created from multiple European datasets.",
    "geoscience_au": "Geoscience Australia's 5-metre resolution DEM, focusing on coastal areas of South Australia, Victoria, and the Northern Territory.",
    "gmted": "Global Multi-Resolution Terrain Elevation Data at resolutions of 7.5\", 15\", and 30\", covering land globally.",
    "kartverket": "Norway’s 10-metre resolution Digital Terrain Model, managed by Kartverket.",
    "mx_lidar": "INEGI’s lidar-based continental relief data for Mexico, offering high accuracy.",
    "ned": "National Elevation Dataset with 10-metre resolution across most of the United States, excluding Alaska.",
    "ned13": "Higher-resolution 3-metre data from the US 3DEP program, available in selected areas.",
    "ned_topobathy": "3-metre resolution dataset of US coastal and water regions, part of the 3DEP initiative.",
    "nrcan_cdem": "Canadian Digital Elevation Model with variable resolutions from 20 to 400 metres depending on latitude, provided by NRCan.",
    "nzlinz": "New Zealand’s LINZ 8-metre resolution elevation model, covering the entire country.",
    "pgdc_5m": "ArcticDEM 5-metre mosaic for polar regions above 60° latitude, covering the Arctic nations.",
    "srtm": "NASA's Shuttle Radar Topography Mission dataset at 30-metre resolution, excluding high latitudes.",
    "uk_lidar": "2-metre resolution lidar dataset over the UK, provided by data.gov.uk.",
}


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

    try:
        logger.info(f"Finding elevation metadata for lat: {lat}, lng: {lng}")

        # Create a Shapely point for the lat/lng
        point = shape({'type': 'Point', 'coordinates': [lng, lat]})

        # Perform Vespa query for documents with bounding boxes containing the point
        query = {
            "yql": f"select resolution, source, geometry from terrarium_sources where contains(bounding_box, {point.wkt}) order by resolution asc;"
        }

        response = requests.get(f"{vespa_query_url}/document/v1/terrarium_sources/query", params=query)
        response.raise_for_status()

        results = response.json()['hits']

        if not results:
            logger.info("No elevation metadata found")
            return {"elevation_resolution": None, "elevation_source": None}

        # Iterate over the fetched results
        for source in results:
            if point.within(shape(json.loads(source['fields']['geometry']))):
                source['fields']['resolution'] = round(source['fields']['resolution'], 1)
                elevation = round(round(elevation / source['fields']['resolution']) * source['fields']['resolution'])
                description = descriptions_map.get(source['fields']['source'], 'No description available')
                return {
                    "elevation": elevation,
                    "elevation_resolution": source['fields']['resolution'],
                    "elevation_source": description
                }

        # If no source contains the point
        logger.info("No source containing the point was found")
        return {"elevation_resolution": None, "elevation_source": None}

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
