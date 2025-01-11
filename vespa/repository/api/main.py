# /main.py
import logging

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse

from .ingestion.processor import start_ingestion_in_background
from .search.processor import visit
from .system.status import get_vespa_status  # Import the function from the status module
from .utils import get_uuid, task_tracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

app = FastAPI()



@app.get("/visit")
async def search_documents(
    doc_type: str = Query(..., description="The document type to filter by"),
    limit: int = Query(50, ge=1, le=10000, description="The number of results to retrieve (max 10,000)"),
    field: str = Query("id", description="The field used for filtering documents"),
    slices: int = Query(1, ge=1, description="The number of slices for parallel processing")
):
    """
    Endpoint to search for documents of a given type with pagination.

    Args:
        doc_type (str): The document type (schema) to query.
        limit (int): The number of documents to retrieve.
        field (str): The field used for filtering; documents must have this field set.
        slices (int): The number of slices for parallel processing.

    Returns:
        JSONResponse: A JSON response with the total document count and the retrieved documents.
    """
    try:
        results = visit(doc_type, limit, field=field, slices=slices)
        return JSONResponse(status_code=200, content=results)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.get("/ingest/{dataset_name}")
async def ingest_dataset(
        dataset_name: str,
        background_tasks: BackgroundTasks,
        limit: int = Query(None, ge=1, description="Optional limit for the number of items to ingest")
):
    """
    Ingest a dataset by name with an optional limit parameter.

    Args:
        limit: The number of items to ingest.
        dataset_name: The name of the dataset to ingest.
        background_tasks (object): BackgroundTasks instance to run tasks in the background.
    """
    task_id = get_uuid()  # Generate a unique task ID

    # Start the ingestion in the background
    background_tasks.add_task(start_ingestion_in_background, dataset_name, task_id, limit)

    return JSONResponse(
        status_code=202,
        content={
            "message": f"Ingestion of {dataset_name} started",
            "task_id": task_id,
            "status_url": f"/status/{task_id}"
        }
    )


@app.get("/status/{task_id}")
async def task_status(task_id: str):
    return task_tracker.get_info(task_id)


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
