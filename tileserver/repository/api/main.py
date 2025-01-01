import logging
import math
from io import BytesIO
from typing import List, Dict, Any

import requests
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils.deletion import delete_tileset
from .utils.kube import restart_tileserver, add_tileset
from .utils.tileset import get_tileset_data, get_all_tileset_data

'''
Dynamically-generated API documentation can be accessed at http://localhost:30081/docs 
'''

# FastAPI app instance
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TilesetRequest(BaseModel):
    type: str
    id: int


class DeleteResponse(BaseModel):
    success: bool
    message: str


class AddResponse(BaseModel):
    status: str


@app.get("/restart", response_model=Dict[str, Any])
def restart():
    """
    Restart the tileserver by sending a SIGHUP signal.

    Returns:
        Dict[str, Any]: A dictionary with 'success' and 'message' keys.
    """
    try:
        return restart_tileserver()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_model=List[Dict[str, Any]])
async def fetch_all_tilesets():
    """
    Fetch tileset data for all datasets and collections.

    Returns:
        List[Dict[str, Any]]: Metadata and information about all tilesets.
    """
    try:
        return await get_all_tileset_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{tileset_type}/{tileset_id}", response_model=Dict[str, Any])
async def fetch_tileset(tileset_type: str, tileset_id: int):
    """
    Fetch tileset data for a specific dataset or collection.

    Args:
        tileset_type (str): The type of tileset (e.g., "datasets" or "collections").
        tileset_id (str): The identifier of the dataset or collection.

    Returns:
        TilesetResponse: Metadata and information about the tileset.
    """
    try:
        return await get_tileset_data(tileset_type, tileset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/{tileset_type}/{tileset_id}", response_model=DeleteResponse)
def remove_tileset(tileset_type: str, tileset_id: int):
    """
    Delete tileset data and associated MBTiles files for a specific dataset or collection.

    Args:
        tileset_type (str): The type of tileset (e.g., "datasets" or "collections").
        tileset_id (str): The identifier of the dataset or collection.

    Returns:
        DeleteResponse: Status of the delete operation.
    """
    try:
        result = delete_tileset(tileset_type, tileset_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting tileset: {str(e)}")


@app.post("/create", response_model=AddResponse)
async def insert_tileset(request: TilesetRequest):
    try:
        result = add_tileset(request.type, request.id)
        return {"status": result}
    except Exception as e:
        return {"status": f"Error adding tileset: {str(e)}"}


@app.get("/elevation/{lat}/{lng}", response_model=Dict[str, Any])
async def get_elevation(lat: float, lng: float):
    """
    Get the elevation at a given latitude and longitude.

    Args:
        lat (float): Latitude in the URL path.
        lng (float): Longitude in the URL path.

    Returns:
        Dict[str, Any]: Elevation data.
    """
    try:
        logger.info(f"Fetching elevation for lat: {lat}, lng: {lng}")

        # Fetch the maxzoom from the tileserver
        terrarium_url = "http://tileserver-gl:8080/data/terrarium.json"
        logger.info(f"Fetching maxzoom from {terrarium_url}")
        metadata_response = requests.get(terrarium_url)
        metadata_response.raise_for_status()
        maxzoom = metadata_response.json().get("maxzoom", 10)
        logger.info(f"Maxzoom fetched: {maxzoom}")

        # Calculate the tile indices
        x = int((lng + 180.0) / 360.0 * (2 ** maxzoom))
        y = int((1.0 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2.0 * (2 ** maxzoom))
        logger.info(f"Tile indices calculated: x={x}, y={y}")

        # Fetch the tile
        tile_url = f"http://tileserver-gl:8080/data/terrarium/{maxzoom}/{x}/{y}.png"
        logger.info(f"Fetching tile from {tile_url}")
        response = requests.get(tile_url)
        response.raise_for_status()
        logger.info("Tile fetched successfully")

        # Decode the image
        tile_image = Image.open(BytesIO(response.content))
        pixel_x = int((lng + 180.0) % 360.0 * (tile_image.width / 360.0))
        pixel_y = int((1.0 - (lat + 90.0) / 180.0) * tile_image.height)
        logger.info(f"Pixel position: x={pixel_x}, y={pixel_y}")

        # Get RGB values
        r, g, b = tile_image.getpixel((pixel_x, pixel_y))
        logger.info(f"RGB values: R={r}, G={g}, B={b}")

        # Calculate elevation based on Terrarium format
        elevation = (r * 256 + g + b / 256) - 32768
        logger.info(f"Calculated elevation: {elevation}")

        return {"latitude": lat, "longitude": lng, "zoom": maxzoom, "elevation": elevation}
    except Exception as e:
        logger.error(f"Error retrieving elevation: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
