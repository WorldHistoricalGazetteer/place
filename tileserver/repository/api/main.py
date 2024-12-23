from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from utils.tileset import get_tileset_data, get_all_tileset_data
from utils.deletion import delete_tileset
from utils.addition import add_tileset

'''
Dynamically-generated API documentation can be accessed at http://localhost:30081/docs 
'''

# TODO:
'''
- pare down the current requirements.txt of the Tippecanoe image
- augment the FastAPI image to include `kubernetes` and `pyyaml` packages
- ? remove the `tippecanoe-job.yaml` template from the Helm chart
'''

# FastAPI app instance
app = FastAPI()


class TilesetRequest(BaseModel):
    type: str
    id: int

class TilesetResponse(BaseModel):
    name: str
    metadata: Dict[str, str]

class AllTilesetsResponse(BaseModel):
    tilesets: List[TilesetResponse]

class DeleteResponse(BaseModel):
    success: bool
    message: str

class AddResponse(BaseModel):
    success: bool
    job_id: str


@app.get("/", response_model=AllTilesetsResponse)
async def fetch_all_tilesets():
    """
    Fetch tileset data for all datasets and collections.

    Returns:
        AllTilesetsResponse: List of all available tilesets with metadata.
    """
    try:
        return await get_all_tileset_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{type}/{id}", response_model=TilesetResponse)
async def fetch_tileset(request: TilesetRequest):
    """
    Fetch tileset data for a specific dataset or collection.

    Args:
        type (str): The type of tileset (e.g., "datasets" or "collections").
        id (str): The identifier of the dataset or collection.

    Returns:
        TilesetResponse: Metadata and information about the tileset.
    """
    try:
        return await get_tileset_data(request.type, request.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/{type}/{id}", response_model=DeleteResponse)
def remove_tileset(request: TilesetRequest):
    """
    Delete tileset data and associated MBTiles files for a specific dataset or collection.

    Args:
        type (str): The type of tileset (e.g., "datasets" or "collections").
        id (str): The identifier of the dataset or collection.

    Returns:
        DeleteResponse: Status of the delete operation.
    """
    try:
        result = delete_tileset(request.type, request.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting tileset: {str(e)}")


@app.post("/", response_model=AddResponse)
async def insert_tileset(request: TilesetRequest):
    try:
        result = add_tileset(request.type, request.id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding tileset: {str(e)}")