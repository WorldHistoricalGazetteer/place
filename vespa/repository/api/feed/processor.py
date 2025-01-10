# /feed/processor.py
import json
import os
import subprocess
import tempfile
from typing import Union, Dict, Any

import httpx

from ..config import namespace
from ..utils import is_valid_url, get_uuid, url_to_tempfile, log_message

# A simple in-memory progress tracker
feed_progress = {}

def log_subprocess_output(command, logger, task_id):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Read the stdout and stderr in real-time
    for stdout_line in iter(process.stdout.readline, ""):
        log_message(
            logger.info, feed_progress, task_id, "stdout",
            stdout_line.strip()
        )
    for stderr_line in iter(process.stderr.readline, ""):
        log_message(
            logger.error, feed_progress, task_id, "stderr",
            stderr_line.strip()
        )

    process.stdout.close()
    process.stderr.close()
    process.wait()  # Wait for the subprocess to complete

    return process.returncode


async def process_documents(doc_type: str, documents: Union[str, Dict[str, Any], list], logger, task_id: str) -> None:
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

    feed_progress[task_id] = {"status": "Processing"}

    if isinstance(documents, dict):  # If it's a single document
        doc_id = documents.get("id", f"id:{namespace}:{doc_type}::{get_uuid()}")
        fields = ','.join([f"{k}:{v}" for k, v in documents.items()])
        command = ["vespa", "document", "put", doc_id, f"fields={fields}"]
    else:
        if isinstance(documents, str):
            if is_valid_url(documents): # If it's a URL
                try:
                    doc_file_path = await url_to_tempfile(documents)
                except httpx.RequestError as e:
                    feed_progress[task_id] = {"status": "Failed", "error": f"Error fetching URL: {str(e)}"}
                    return
            elif os.path.isfile(documents): # If it's a file path
                doc_file_path = documents
            else:
                feed_progress[task_id] = {"status": "Failed",
                                          "error": f"Provided string ({documents}) is neither a valid URL nor a file path."}
                return
        elif isinstance(documents, list):  # If it's a list of documents
            documents = [{"id": f"id:{namespace}:{doc_type}::{get_uuid()}", **doc} for doc in documents]
            with tempfile.NamedTemporaryFile(delete=False) as doc_file:
                json.dump(documents, doc_file)
                doc_file.seek(0)
                doc_file_path = doc_file.name
        command = ["vespa", "feed", doc_file_path, "--verbose"]

    feed_progress[task_id] = {"status": "Feeding"}

    try:
        returncode = log_subprocess_output(command, logger, task_id)

        if returncode == 0:
            feed_progress[task_id] = {"status": "Completed"}
        else:
            feed_progress[task_id] = {"status": "Failed"}
    except Exception as e:
        feed_progress[task_id] = {"status": "Failed", "error": str(e)}
    finally:
        if doc_file_path and not os.path.isfile(documents): # Clean up any temporary file, but not any passed file
            os.remove(doc_file_path)
