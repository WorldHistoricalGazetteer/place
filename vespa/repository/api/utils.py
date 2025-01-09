# /utils.py
import tempfile
import uuid
from typing import Callable, Dict, Any
from urllib.parse import urlparse

import httpx


def is_valid_url(url: str) -> bool:
    """
    Check if the provided URL has a valid format.
    """
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme) and bool(parsed_url.netloc)


def get_uuid() -> str:
    """
    Generate a unique identifier.
    """
    return str(uuid.uuid4())


async def url_to_tempfile(url: str) -> str:
    """
    Fetch data from the given URL asynchronously.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(response.content)
                return tmp_file.name
        except httpx.RequestError as e:
            raise Exception(f"Error fetching URL: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.text}")
        except Exception as e:
            raise Exception(f"An error occurred: {str(e)}")


def log_message(
        log_method: Callable[[str], None],
        progress_monitor: Dict[str, Any] = None,
        task_id: str = None,
        status: str = None,
        message: str = None
) -> Dict[str, Any]:
    """
    Logs a message using the specified log method and optionally updates a progress monitor.

    :param log_method: The logger method to use (e.g., logger.info, logger.exception)
    :param progress_monitor: Optional dictionary to track progress
    :param task_id: Task ID for tracking progress
    :param status: Status message to update in the progress monitor
    :param message: Log message
    :return: Updated progress entry or None
    """
    log_method(message)
    if progress_monitor is not None and task_id is not None:
        progress_monitor[task_id] = {"status": status, "message": message}
        return progress_monitor[task_id]
    return {"status": status, "message": message}
