# /utils.py
import asyncio
import uuid
from typing import Dict
from urllib.parse import urlparse

# Global dictionary to store background tasks by task_id (for tracking purposes)
background_tasks: Dict[str, asyncio.Task] = {}


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
