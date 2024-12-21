from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import logging

app = FastAPI()

# Define Pydantic model to validate response data structure
class TilesMetadata(BaseModel):
    tiles: dict

# Enable logging
logging.basicConfig(level=logging.DEBUG)

# Endpoint to fetch data from Tileserver-GL
@app.get("/whg", response_model=TilesMetadata)
async def get_tileserver_status():
    url = "http://tileserver-gl:8080/styles/whg-enhanced/style.json"
    logging.debug(f"Requesting URL: {url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()  # Raises an exception for 4xx/5xx responses
            return TilesMetadata(tiles=response.json())
    except httpx.RequestError as e:
        logging.error(f"RequestError fetching data from tileserver-gl: {e}")
        return {"error": f"RequestError fetching data from tileserver-gl: {str(e)}"}
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTPStatusError fetching data from tileserver-gl: {e}")
        return {"error": f"HTTPStatusError fetching data from tileserver-gl: {str(e)}"}
