# /main.py
import logging

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Path
from fastapi.responses import JSONResponse

from .gis.intersections import GeometryIntersect
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


@app.get("/iso3166/{latitude}/{longitude}")
async def get_country_codes(
    latitude: float = Path(..., description="Latitude of the point"),
    longitude: float = Path(..., description="Longitude of the point"),
):
    """
    Returns a list of country codes for a given latitude and longitude.
    """
    try:
        geometry = {
            "type": "Point",
            "coordinates": [longitude, latitude]
        }
        bbox = {
            "bbox_sw_lat": latitude - 0.01,
            "bbox_sw_lng": longitude - 0.01,
            "bbox_ne_lat": latitude + 0.01,
            "bbox_ne_lng": longitude + 0.01,
        }
        results = GeometryIntersect(geometry=geometry, bbox=bbox).resolve()
        return JSONResponse(content={"country_codes": [result["code2"] for result in results if not result["code2"]=="-"]})
    except Exception as e:
        logger.error(f"Error in /iso3166: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch country codes: {e}"})


@app.get("/terrarium/{latitude}/{longitude}")
async def get_terrarium_object(
    latitude: float = Path(..., description="Latitude of the point"),
    longitude: float = Path(..., description="Longitude of the point"),
):
    """
    Returns the terrarium object with the smallest resolution for the given latitude and longitude.
    """
    try:
        geometry = {
            "type": "Point",
            "coordinates": [longitude, latitude]
        }
        bbox = {
            "bbox_sw_lat": latitude - 0.01,
            "bbox_sw_lng": longitude - 0.01,
            "bbox_ne_lat": latitude + 0.01,
            "bbox_ne_lng": longitude + 0.01,
        }
        results = GeometryIntersect(
            geometry=geometry, bbox=bbox, schema="terrarium", fields="resolution,source"
        ).resolve()
        if not results:
            return JSONResponse(content={"error": "No terrarium object found"})
        return JSONResponse(content=results[0])
    except Exception as e:
        logger.error(f"Error in /terrarium: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Failed to fetch terrarium object: {e}"})


@app.get("/visit")
async def visit_documents(
        schema: str = Query(..., description="The document type to filter by"),
        namespace: str = Query(None, description="The Vespa namespace to query"),
        limit: int = Query(50, ge=1, le=10000, description="The number of results to retrieve (max 10,000); use -1 for no limit"),
        slices: int = Query(1, ge=1, description="The number of slices for parallel processing")
):
    """
    Endpoint to search for documents of a given type with pagination.

    Args:
        schema (str): The document type (schema) to query.
        namespace (str): The Vespa namespace to query.
        limit (int): The number of documents to retrieve; use -1 for no limit.
        slices (int): The number of slices for parallel processing.

    Returns:
        JSONResponse: A JSON response with the total document count and the retrieved documents.
    """
    try:
        results = visit(schema, namespace, limit, slices)
        return JSONResponse(status_code=200, content=results)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.get("/ingest/{dataset_name}")
async def ingest_dataset(
        dataset_name: str,
        background_tasks: BackgroundTasks,
        limit: int = Query(None, ge=1, description="Optional limit for the number of items to ingest"),
        delete_only: bool = Query(False, description="Delete existing data without ingestion")
):
    """
    Ingest a dataset by name with an optional limit parameter.

    Args:
        limit: The number of items to ingest.
        dataset_name: The name of the dataset to ingest.
        background_tasks (object): BackgroundTasks instance to run tasks in the background.
        delete_only: If True, delete existing data without ingestion.
    """
    task_id = get_uuid()  # Generate a unique task ID

    # Start the ingestion in the background
    background_tasks.add_task(start_ingestion_in_background, dataset_name, task_id, limit, delete_only)

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
