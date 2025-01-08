# /main.py

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from system.status import get_vespa_status  # Import the function from the status module

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
