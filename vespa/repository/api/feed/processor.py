# /feed/processor.py

import uuid
from typing import Union, Dict, Any

import httpx

from ..config import host_mapping

# A simple in-memory progress tracker
feed_progress = {}


async def send_to_vespa_feed(data: Dict[str, Any]) -> Dict:
    """
    Send the provided data to the Vespa feed endpoint.
    """
    feed_url = f"{host_mapping['feed']}/document/v1/your_namespace/your_document_type/docid/{data['id']}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(feed_url, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            raise Exception(f"Error contacting Vespa feed: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.text}")


def process_documents(documents: Union[Dict[str, Any], list, str], task_id: str) -> None:
    """
    Process the documents and send them to the Vespa feed endpoint.
    """
    feed_progress[task_id] = {"status": "In Progress", "processed": 0, "total": 0}

    if isinstance(documents, str):  # If it's a URL
        try:
            # Fetch data from the URL
            response = httpx.get(documents)
            response.raise_for_status()
            documents = response.json()
        except httpx.RequestError as e:
            feed_progress[task_id] = {"status": "Failed", "error": f"Error fetching URL: {str(e)}"}
            return

    if isinstance(documents, list):  # If it's a list of documents
        feed_progress[task_id]["total"] = len(documents)
        for document in documents:
            try:
                send_to_vespa_feed(document)
                feed_progress[task_id]["processed"] += 1
            except Exception as e:
                feed_progress[task_id] = {"status": "Failed", "error": str(e)}
                return
    elif isinstance(documents, dict):  # If it's a single document
        feed_progress[task_id]["total"] = 1
        try:
            send_to_vespa_feed(documents)
            feed_progress[task_id]["processed"] = 1
        except Exception as e:
            feed_progress[task_id] = {"status": "Failed", "error": str(e)}
            return

    feed_progress[task_id]["status"] = "Completed"


def generate_task_id() -> str:
    """
    Generate a unique task ID for each feed operation.
    """
    return str(uuid.uuid4())
