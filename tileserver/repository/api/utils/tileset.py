import httpx
from pathlib import Path
import json
from typing import Dict, Any, Union
from pydantic import BaseModel, ValidationError

CONFIG_DIR = "/mnt/data/configs"
CONFIG_FILE = Path(CONFIG_DIR) / "config.json"


class VectorLayer(BaseModel):
    id: str
    description: str
    minzoom: int
    maxzoom: int
    fields: Dict[str, str]

class TilestatsAttribute(BaseModel):
    attribute: str
    count: int
    type: str
    values: list
    min: Union[int, float, None]
    max: Union[int, float, None]

class TilestatsLayer(BaseModel):
    layer: str
    count: int
    geometry: str
    attributeCount: int
    attributes: list[TilestatsAttribute]

class Tilestats(BaseModel):
    layerCount: int
    layers: list[TilestatsLayer]

class TilesetData(BaseModel):
    tiles: list[str]
    name: str
    format: str
    basename: str
    id: str
    description: str
    version: str
    minzoom: int
    maxzoom: int
    center: list[float]
    bounds: list[float]
    type: str
    attribution: str
    generator: str
    generator_options: str
    vector_layers: list[VectorLayer]
    tilestats: Tilestats
    tilejson: str

async def get_tileset_data(tileset_type: str, tileset_id: int) -> Union[TilesetData, Dict[str, str]]:
    """
    Fetch specific tileset data from the Tileserver-GL.

    Args:
        tileset_type (str): The type of the tileset (e.g., "datasets" or "collections").
        tileset_id (str): The ID of the tileset.

    Returns:
        Union[TilesetData, Dict[str, str]]: A parsed tileset data object or an error message.
    """
    url = f"http://tileserver-gl:8080/data/{tileset_type}-{tileset_id}.json"

    try:
        # Asynchronous HTTP request to fetch tileset data
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()

        # Parse and validate the JSON response using the TilesetData model
        return TilesetData(**response.json())

    except httpx.HTTPStatusError as e:
        # Handle HTTP errors and return a meaningful error message
        return {"error": f"HTTP error occurred: {str(e)}", "status_code": e.response.status_code}

    except httpx.RequestError as e:
        # Handle connection issues or timeout errors
        return {"error": f"Request error occurred: {str(e)}"}

    except Exception as e:
        # Catch-all for unexpected errors
        return {"error": f"An unexpected error occurred: {str(e)}"}


class TilesetEntry(BaseModel):
    """
    Represents a single entry in the tileset configuration.
    """
    mbtiles: str
    tilejson: Dict[str, str]  # Must contain at least 'attribution', but could include more fields.


async def get_all_tileset_data() -> Dict[str, Any]:
    """
    Fetch all tileset data from the configuration file.

    The returned data includes only entries under the "data" section
    whose keys start with "datasets-" or "collections-", and ensures
    that each entry has at least "mbtiles" and "tilejson" properties.
    Additional properties in the configuration are preserved but optional.

    Returns:
        Dict[str, Any]: A dictionary containing filtered and validated tileset data.
                        Returns an empty list for tilesets if the configuration file
                        does not exist or is invalid.
    """

    # Return an empty tileset list if the config file does not exist
    if not CONFIG_FILE.exists():
        return {"tilesets": []}

    try:
        # Load configuration data
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)

        # Extract and filter relevant data
        config_data = config.get("data", {})
        filtered_data = []

        for key, value in config_data.items():
            if key.startswith("datasets-") or key.startswith("collections-"):
                try:
                    # Manually validate the required fields within the nested entry
                    if "mbtiles" in value and "tilejson" in value:
                        validated_entry = TilesetEntry(**value)
                        filtered_data.append({"key": key, **validated_entry.model_dump()})
                    else:
                        print(f"Missing required fields for {key}: 'mbtiles' or 'tilejson'")
                except ValidationError as e:
                    print(f"Invalid tileset entry for {key}: {e}")

        return {"tilesets": filtered_data}

    except (json.JSONDecodeError, KeyError) as e:
        # Handle JSON parsing errors or missing keys gracefully
        return {"error": f"Failed to load tileset data: {str(e)}"}

    except Exception as e:
        # Catch-all for unexpected errors
        return {"error": f"An unexpected error occurred: {str(e)}"}
