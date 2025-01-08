# /feed/processor.py
import json
import os
import subprocess
import tempfile
from typing import Union, Dict, Any

import httpx
import ijson

from ..config import namespace
from ..utils import is_valid_url, get_uuid, url_to_tempfile

# A simple in-memory progress tracker
feed_progress = {}


async def process_documents(doc_type: str, documents: Union[str, Dict[str, Any], list], task_id: str) -> None:
    """
    Process the documents by one of the following methods:
    - Fetching data from a URL
    - Processing a local file
    - Processing a list of documents
    - Processing a single document

    Add IDs to documents where absent.

    Feed the processed documents to Vespa asynchronously.

    Avoids loading large files into memory by use of ijson.
    """

    doc_file_path = None
    processed_file = None

    if isinstance(documents, dict):  # If it's a single document
        doc_id = documents.get("id", f"id:{namespace}:{doc_type}::{get_uuid()}")
        fields = ','.join([f"{k}:{v}" for k, v in documents.items()])
        command = ["vespa", "document", "put", doc_id, f"fields={fields}"]
    else:
        if isinstance(documents, str):
            if is_valid_url(documents):
                try:
                    doc_file_path = await url_to_tempfile(documents)
                except httpx.RequestError as e:
                    feed_progress[task_id] = {"status": "Failed", "error": f"Error fetching URL: {str(e)}"}
                    return
            elif os.path.isfile(documents):
                with open(documents, "r") as f:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        tmp_file.write(f.read())
                        doc_file_path = tmp_file.name
            else:
                feed_progress[task_id] = {"status": "Failed",
                                          "error": f"Provided string ({documents}) is neither a valid URL nor a file path."}
                return
            with open(doc_file_path, "rb") as f, tempfile.NamedTemporaryFile(delete=False) as processed_file:
                objects = ijson.items(f, '')
                for obj in objects:
                    if "id" not in obj:
                        obj["id"] = f"id:{namespace}:{doc_type}::{get_uuid()}"
                    json.dump(obj, processed_file)
                    processed_file.write(b"\n")
        elif isinstance(documents, list):  # If it's a list of documents
            documents = [{"id": f"id:{namespace}:{doc_type}::{get_uuid()}", **doc} for doc in documents]
            with tempfile.NamedTemporaryFile(delete=False) as processed_file:
                json.dump(documents, processed_file)
                processed_file.seek(0)
        command = ["vespa", "feed", processed_file.name]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0:
            feed_progress[task_id] = {"status": "Completed", "output": result.stdout}
        else:
            feed_progress[task_id] = {"status": "Failed", "error": result.stderr}
    except Exception as e:
        feed_progress[task_id] = {"status": "Failed", "error": str(e)}
    finally:
        if doc_file_path:
            os.remove(doc_file_path)
        if processed_file:
            os.remove(processed_file.name)
