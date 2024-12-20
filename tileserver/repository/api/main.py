# Placeholder script for the main API
# This script will be the main entry point for the API and is embedded in the container image when created.
# Updates to this script can be mounted into the container image at runtime.

from fastapi import FastAPI
from pydantic import BaseModel
import httpx

app = FastAPI()

# Define Pydantic model to validate response data structure
class TilesMetadata(BaseModel):
    tiles: dict

# Endpoint to fetch data from Tileserver-GL
@app.get("/tileserver-status", response_model=TilesMetadata)
async def get_tileserver_status():
    url = "http://tileserver:8081/tiles"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()  # Raises an exception for 4xx/5xx responses
        return TilesMetadata(tiles=response.json())
