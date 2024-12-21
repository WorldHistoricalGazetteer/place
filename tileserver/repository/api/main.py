import logging
from fastapi import FastAPI
from pydantic import BaseModel
import httpx

# Set up the root logger with a custom format
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Set up Uvicorn's logger to follow the same format
uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
uvicorn_logger.addHandler(console_handler)

# FastAPI app instance
app = FastAPI()

# Define Pydantic model to validate response data structure
class TilesMetadata(BaseModel):
    tiles: dict

# Endpoint to fetch data from Tileserver-GL
@app.get("/whg", response_model=TilesMetadata)
async def get_tileserver_status():
    url = "http://tileserver-gl:8080/styles/whg-enhanced/style.json"
    # Log the request
    logging.debug(f"Requesting URL: {url}")
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()  # Raises an exception for 4xx/5xx responses
        # Log the response
        logging.debug(f"Response received: {response.status_code}")
        return TilesMetadata(tiles=response.json())
