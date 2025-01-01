import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any

import rtree
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils.deletion import delete_tileset
from .utils.kube import restart_tileserver, add_tileset
from .utils.terrarium_elevation import get_elevation_data, init_elevation_data
from .utils.tileset import get_tileset_data, get_all_tileset_data

'''
Dynamically-generated API documentation can be accessed at http://localhost:30081/docs 
'''

# FastAPI app instance
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for the elevation data and the associated RTree index
bounds_map = {}
geometry_map = {}
properties_map = {}
descriptions_map = {}
idx = rtree.index.Index()


class TilesetRequest(BaseModel):
    type: str
    id: int


class DeleteResponse(BaseModel):
    success: bool
    message: str


class AddResponse(BaseModel):
    status: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform startup tasks
    init_elevation_data()
    yield


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
        elevation_data = get_elevation_data(lat, lng)
        return elevation_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
