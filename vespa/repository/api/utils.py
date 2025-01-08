# /utils.py
import tempfile
import uuid
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
