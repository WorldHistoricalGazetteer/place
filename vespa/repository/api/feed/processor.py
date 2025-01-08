# /feed/processor.py

import uuid
from typing import Union, Dict, Any

import httpx

from ..config import namespace, host_mapping
from ..utils import is_valid_url, get_uuid

# A simple in-memory progress tracker
feed_progress = {}


async def send_to_vespa_feed(doc_type: str, data: Dict[str, Any]) -> Dict:
    """
    Send the provided data to the Vespa feed endpoint.
    """
    if 'id' not in data:
        data['id'] = get_uuid()
    feed_url = f"{host_mapping['feed']}/document/v1/{namespace}/{doc_type}/docid/{data['id']}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(feed_url, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            raise Exception(f"Error contacting Vespa feed: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.text}")


async def fetch_data_from_url(url: str) -> Dict:
    """
    Fetch data from the given URL asynchronously.
    """

    if not is_valid_url(url):
        raise ValueError(f"Invalid URL format: {url}")

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def process_documents(doc_type: str, documents: Union[Dict[str, Any], list, str], task_id: str) -> None:
    """
    Process the documents and send them to the Vespa feed endpoint.
    """
    feed_progress[task_id] = {"status": "In Progress", "processed": 0, "total": 0}

    if isinstance(documents, str):  # If it's a URL
        try:
            documents = await fetch_data_from_url(documents)  # Use async fetch function
        except httpx.RequestError as e:
            feed_progress[task_id] = {"status": "Failed", "error": f"Error fetching URL: {str(e)}"}
            return

    if isinstance(documents, list):  # If it's a list of documents
        feed_progress[task_id]["total"] = len(documents)
        for document in documents:
            try:
                await send_to_vespa_feed(doc_type, document)
                feed_progress[task_id]["processed"] += 1
            except Exception as e:
                feed_progress[task_id] = {"status": "Failed", "error": str(e)}
                return
    elif isinstance(documents, dict):  # If it's a single document
        feed_progress[task_id]["total"] = 1
        try:
            await send_to_vespa_feed(doc_type, documents)
            feed_progress[task_id]["processed"] = 1
        except Exception as e:
            feed_progress[task_id] = {"status": "Failed", "error": str(e)}
            return

    feed_progress[task_id]["status"] = "Completed"
