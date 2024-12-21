from fastapi import FastAPI
from pydantic import BaseModel
import httpx

# FastAPI app instance
app = FastAPI()

# Define Pydantic model to validate response data structure
class TilesMetadata(BaseModel):
    tiles: dict

# Endpoint to fetch data from Tileserver-GL
@app.get("/whg-enhanced", response_model=TilesMetadata)
async def get_tileserver_status():
    url = "http://tileserver-gl:8080/styles/whg-enhanced/style.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()  # Raises an exception for 4xx/5xx responses
        return TilesMetadata(tiles=response.json())

# TODO: Create endpoint to fetch mapdata from Django API and send as Job to Tippecanoe.

# TODO: Create endpoints to replicate the functionality of the existing `utils`.
