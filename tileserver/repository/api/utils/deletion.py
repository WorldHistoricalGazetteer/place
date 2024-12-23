from pathlib import Path
import json
from pydantic import BaseModel
import logging
from .kubernetes import restart_tileserver

# Constants
CONFIG_DIR = "/mnt/data/configs"
TILES_DIR = "/mnt/data/tiles"
CONFIG_FILE = Path(CONFIG_DIR) / "config.json"

# Configure logging
logger = logging.getLogger("tileserver.deletion")
logger.setLevel(logging.INFO)  # Set to DEBUG for more detailed logs
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s"
)
handler.setFormatter(formatter)
if not logger.hasHandlers():
        logger.addHandler(handler)

class DeleteResponse(BaseModel):
    success: bool
    message: str
    

def delete_tileset(tileset_type: str, tileset_id: int) -> DeleteResponse:
    """
    Delete tileset data and associated MBTiles files for a specific dataset or collection.

    Args:
        tileset_type (str): The type of tileset (e.g., "dataset" or "collection").
        tileset_id (str): The identifier of the dataset or collection.

    Returns:
        DeleteResponse: Status of the delete operation.
    """
    # Construct the tileset key
    tileset_key = f"{tileset_type}-{tileset_id}"
    logger.info(f"Attempting to delete tileset: {tileset_key}")

    # Load the configuration file
    if not CONFIG_FILE.exists():
        message = f"Configuration file not found: {CONFIG_FILE}"
        logger.warning(message)
        return DeleteResponse(success=False, message=message)

    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)
        logger.debug("Loaded configuration file successfully.")
    except json.JSONDecodeError as e:
        message = f"Invalid JSON in configuration file: {str(e)}"
        logger.error(message)
        return DeleteResponse(success=False, message=message)
    except Exception as e:
        message = f"Error reading configuration file: {str(e)}"
        logger.error(message)
        return DeleteResponse(success=False, message=message)

    # Remove the tileset entry from the config
    tilesets = config.get("data", {})
    if tileset_key not in tilesets:
        message = f"Tileset key '{tileset_key}' not found in configuration."
        logger.warning(message)
        return DeleteResponse(success=False, message=message)

    try:
        del tilesets[tileset_key]
        logger.info(f"Removed tileset '{tileset_key}' from configuration.")
    except Exception as e:
        message = f"Failed to remove tileset '{tileset_key}' from configuration: {str(e)}"
        logger.error(message)
        return DeleteResponse(success=False, message=message)

    # Save the updated configuration back to the file
    try:
        with CONFIG_FILE.open("w") as f:
            json.dump(config, f, indent=4)
        logger.info(f"Updated configuration file: {CONFIG_FILE}")
    except Exception as e:
        message = f"Failed to update configuration file: {str(e)}"
        logger.error(message)
        return DeleteResponse(success=False, message=message)

    # Restart the tileserver with a SIGHUP signal and check health
    restart_result = restart_tileserver()
    if not restart_result["success"]:
        logger.error(f"Failed to restart tileserver: {restart_result['message']}")
        return DeleteResponse(success=False, message=f"Failed to restart tileserver: {restart_result['message']}")
    logger.info("Tileserver restart successful.")

    # Construct the path to the MBTiles file
    mbtiles_path = Path(TILES_DIR) / f"{tileset_type}/{tileset_id}.mbtiles"
    logger.debug(f"MBTiles path: {mbtiles_path}")

    # Check if the MBTiles file exists
    if not mbtiles_path.exists():
        message = f"Tileset MBTiles file not found: {mbtiles_path}"
        logger.warning(message)
        return DeleteResponse(success=False, message=message)

    # Attempt to delete the MBTiles file
    try:
        mbtiles_path.unlink()
        logger.info(f"Deleted MBTiles file: {mbtiles_path}")
    except Exception as e:
        message = f"Failed to delete MBTiles file: {mbtiles_path}. Error: {str(e)}"
        logger.error(message)
        return DeleteResponse(success=False, message=message)

    message = f"Successfully deleted tileset '{tileset_key}'."
    logger.info(message)
    return DeleteResponse(success=True, message=message)
