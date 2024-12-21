import logging
from fastapi import FastAPI
from pydantic import BaseModel
import httpx

# Configure the logger
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.DEBUG)  # You can adjust the log level here
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler = logging.StreamHandler()

console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

app = FastAPI()

# Define Pydantic model to validate response data structure
class TilesMetadata(BaseModel):
    tiles: dict

# Endpoint to fetch data from Tileserver-GL
@app.get("/whg-enhanced", response_model=TilesMetadata)
async def get_tileserver_status():
    url = "http://tileserver-gl:8080/styles/whg-enhanced/style.json"
    logger.debug(f"Requesting URL: {url}")  # Custom log entry
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()  # Raises an exception for 4xx/5xx responses
        logger.debug(f"Response received: {response.status_code}")
        return TilesMetadata(tiles=response.json())
