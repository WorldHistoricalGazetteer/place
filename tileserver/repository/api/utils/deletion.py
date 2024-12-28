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
    tileset_path = f"{tileset_type}/{tileset_id}"
    logger.info(f"Attempting to delete tileset: {tileset_path}")

    # Construct the path to the MBTiles file
    mbtiles_path = Path(TILES_DIR) / f"{tileset_path}.mbtiles"
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

    # Restart the tileserver (triggers a rebuild of config.json)
    restart_result = restart_tileserver()
    if not restart_result["success"]:
        logger.error(f"Failed to restart tileserver: {restart_result['message']}")
        return DeleteResponse(success=False, message=f"Failed to restart tileserver: {restart_result['message']}")
    logger.info("Tileserver restart successful.")

    message = f"Successfully deleted tileset '{tileset_path}'."
    logger.info(message)
    return DeleteResponse(success=True, message=message)
