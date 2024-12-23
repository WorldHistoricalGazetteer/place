import json
import ijson
from pathlib import Path
import logging

import requests
from fastapi import HTTPException

from .kubernetes import restart_tileserver, start_tippecanoe_job

# Constants
CONFIG_DIR = "/mnt/data/configs"
TILES_DIR = "/mnt/data/tiles"
CONFIG_FILE = Path(CONFIG_DIR) / "config.json"

# Configure logging
logger = logging.getLogger("tileserver.addition")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)


def add_tileset(tileset_type: str, tileset_id: int) -> dict:
    """
    Add a tileset by invoking Tippecanoe and updating the config.json.

    Args:
        tileset_type (str): The type of tileset (e.g., "datasets" or "collections").
        tileset_id (int): The identifier of the dataset or collection.

    Returns:
        dict: A dictionary containing 'success' and 'status' indicators.
    """

    # Construct the tileset key
    tileset_key = f"{tileset_type}-{tileset_id}"
    logger.info(f"Adding tileset: {tileset_key}")

    mapdata_url = "http://django-service.whg.svc.cluster.local:8000/mapdata/{tileset_type}/{tileset_id}/tileset/"
    try:
        logger.info(f"Fetching data from {mapdata_url}")
        response = requests.get(mapdata_url, stream=True)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch data from {mapdata_url}: {e}")
        return {"success": False, "status": f"Failed to fetch data: {str(e)}"}

    # Use ijson to parse and extract specific fields (efficient memory-use for large datasets)
    logger.info("Parsing JSON response for relevant fields")
    citation_data = {}
    try:
        for prefix, event, value in ijson.parse(response.raw):
            if prefix in {'title', 'citation', 'creator', 'contributors'} and event == 'string':
                citation_data[prefix] = value
    except Exception as e:
        logger.error(f"Error while parsing JSON: {e}")
        return {"success": False, "status": f"Error parsing JSON: {str(e)}"}
    logger.info(f"Citation data: {citation_data}")

    # Extract name and attribution from the GeoJSON properties
    name = f"{tileset_id}{citation_data.get('title', '')}"
    attribution = ''
    try:
        if citation_data.get('citation'):
            attribution = citation_data['citation']
        else:
            if citation_data.get('creator') and citation_data.get('contributors'):
                attribution = f"{citation_data['title']}: {citation_data['creator']}, {citation_data['contributors']}"
            elif citation_data.get('creator'):
                attribution = f"{citation_data['title']}: {citation_data['creator']}"
            elif citation_data.get('contributors'):
                attribution = f"{citation_data['title']}: {citation_data['contributors']}"
    except Exception as e:
        return {"success": False, "status": f"Failed to set attribution string: {str(e)}"}

    # Start Tippecanoe job
    job_id = start_tippecanoe_job(tileset_type, tileset_id, mapdata_url, name, attribution)
    logger.info(f"Tippecanoe job started with Job ID: {job_id}")

    # Load the configuration file
    if not CONFIG_FILE.exists():
        return {"success": False, "status": f"Configuration file not found: {CONFIG_FILE}"}

    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
        logger.debug("Loaded configuration file successfully.")
    except json.JSONDecodeError as e:
        return {"success": False, "status": f"Invalid JSON in configuration file: {str(e)}"}

    # Update the configuration with the new tileset
    config.setdefault("data", {})[tileset_key] = {"mbtiles": f"{tileset_id}.mbtiles", "tilejson": {"attribution": attribution}}
    try:
        with CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"Updated configuration file: {CONFIG_FILE}")
    except Exception as e:
        return {"success": False, "status": f"Failed to update configuration file: {str(e)}"}

    # Restart the tileserver to pick up the new configuration
    try:
        restart_tileserver()
        logger.info("Tileserver restarted successfully.")
    except Exception as e:
        return {"success": False, "status": f"Failed to restart tileserver: {str(e)}"}

    return {"success": True, "status": job_id}
