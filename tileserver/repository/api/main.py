import logging
from typing import List, Dict, Any

import rtree
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .utils.deletion import delete_tileset
from .utils.kube import restart_tileserver, add_tileset
from .utils.terrarium_elevation import get_elevation_data, lifespan
from .utils.tileset import get_tileset_data, get_all_tileset_data

'''
Dynamically-generated API documentation can be accessed at http://localhost:30081/docs 
'''

# FastAPI app instance
app = FastAPI(lifespan=lifespan)

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


@app.get("/restart", response_model=Dict[str, Any])
def restart():
    """
    Restart the tileserver.

    Sends a SIGHUP signal to the tileserver process to reload its configuration.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'success' (bool): Indicates if the operation was successful.
            - 'message' (str): Details about the operation result.
    """
    try:
        return restart_tileserver()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_model=List[Dict[str, Any]])
async def fetch_all_tilesets():
    """
    Retrieve metadata for all tilesets.

    Queries and returns information about all available datasets and collections.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing metadata for a tileset.
    """
    try:
        return await get_all_tileset_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{tileset_type}/{tileset_id}", response_model=Dict[str, Any])
async def fetch_tileset(tileset_type: str, tileset_id: int):
    """
    Retrieve metadata for a specific tileset.

    Args:
        tileset_type (str): Type of tileset ('datasets' or 'collections').
        tileset_id (int): Identifier of the tileset.

    Returns:
        Dict[str, Any]: A dictionary containing metadata for the specified tileset.
    """
    try:
        return await get_tileset_data(tileset_type, tileset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/{tileset_type}/{tileset_id}", response_model=DeleteResponse)
def remove_tileset(tileset_type: str, tileset_id: int):
    """
    Delete a specific tileset.

    Removes tileset data and its associated MBTiles files from the server.

    Args:
        tileset_type (str): Type of tileset ('datasets' or 'collections').
        tileset_id (int): Identifier of the tileset.

    Returns:
        DeleteResponse: An object containing:
            - 'success' (bool): Indicates if the deletion was successful.
            - 'message' (str): Details about the deletion operation.
    """
    try:
        result = delete_tileset(tileset_type, tileset_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting tileset: {str(e)}")


@app.post("/create", response_model=AddResponse)
async def insert_tileset(request: TilesetRequest):
    """
    Add a new tileset.

    Inserts a tileset into the server by specifying its type and identifier.

    Args:
        request (TilesetRequest): Request payload containing:
            - type (str): Type of the tileset ('datasets' or 'collections').
            - id (int): Identifier of the tileset.

    Returns:
        AddResponse: An object containing the status of the operation.
    """
    try:
        result = add_tileset(request.type, request.id)
        return {"status": result}
    except Exception as e:
        return {"status": f"Error adding tileset: {str(e)}"}


@app.get("/elevation/{lat_string}/{lng_string}", response_model=Dict[str, Any])
async def get_elevation(lat_string: str, lng_string: str):
    """
    Retrieve elevation data for a given location.

    Calculates the elevation, resolution, and source information for a specific latitude and longitude.

    Args:
        lat_string (str): Latitude of the location (use of string preserves implied precision).
        lng_string (str): Longitude of the location (use of string preserves implied precision).

    Returns:
        Dict[str, Any]: A dictionary containing:
            - 'elevation' (float): Elevation in metres.
            - 'ground_resolution' (float): Ground resolution in metres.
            - 'elevation_resolution' (float): Elevation resolution in metres.
            - 'elevation_source' (str): Description of the elevation data source.
            - 'units' (str): Measurement units ('metres').
    """
    try:
        elevation_data = get_elevation_data(lat_string, lng_string)
        return elevation_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving elevation: {str(e)}")
