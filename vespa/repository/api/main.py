# /main.py

from typing import Union, Dict, Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from .feed.processor import process_documents, feed_progress  # Import feed processing functions
from .system.status import get_vespa_status  # Import the function from the status module
from .utils import get_uuid

app = FastAPI()


@app.get("/status")
async def get_status():
    """
    Returns the detailed status of the Vespa containers as JSON.
    """
    try:
        statuses = await get_vespa_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching status: {str(e)}")

    return JSONResponse(
        status_code=200,
        content=statuses,
    )


@app.post("/feed")
async def feed_data(doc_type: str, data: Union[Dict[str, Any], list, str], background_tasks: BackgroundTasks):
    """
    Accepts the data to be fed to the Vespa feed container, identifies the type of input (single document, array, or URL),
    and starts the feeding process asynchronously.
    """
    task_id = get_uuid()  # Generate a unique task ID

    # Add the background task to process the feed data
    background_tasks.add_task(process_documents, doc_type, data, task_id)

    return JSONResponse(
        status_code=202,
        content={
            "message": "Data feeding started",
            "task_id": task_id,
            "status_url": f"/status/{task_id}"
        }
    )


@app.get("/feed/status/{task_id}")
async def feed_status(task_id: UUID):
    """
    Endpoint to check the status of a feed operation by task ID.
    """
    task_id_str = str(task_id)
    progress = feed_progress.get(task_id_str)

    if not progress:
        raise HTTPException(status_code=404, detail=f"Task {task_id_str} not found.")

    return JSONResponse(status_code=200, content=progress)
