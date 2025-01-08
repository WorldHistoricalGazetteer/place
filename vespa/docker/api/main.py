# Placeholder script for the main API
# This script will be the main entry point for the API and is embedded in the container image when created.
# Updates to this script can be mounted into the container image at runtime.
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
from typing import Dict

app = FastAPI()

# Vespa container hosts
host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST", "http://vespa-query-container-0.vespa-internal.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed-container-0.vespa-internal.vespa.svc.cluster.local:8080"),
}

def extract_status(data: Dict) -> Dict:
    """
    Extract relevant status details from the Vespa ApplicationStatus response.
    """
    try:
        version = data["application"]["vespa"]["version"]
        meta_date = data["application"]["meta"]["date"]
        generation = data["application"]["meta"]["generation"]
        return {
            "vespa_version": version,
            "last_updated": meta_date,
            "generation": generation,
        }
    except KeyError as e:
        raise ValueError(f"Missing key in response: {e}")

@app.get("/status")
async def get_status():
    """
    Returns the detailed status of the Vespa containers as JSON.
    """
    async with httpx.AsyncClient() as client:
        statuses = {}
        try:
            for host_type, host_url in host_mapping.items():
                response = await client.get(f"{host_url}/ApplicationStatus")
                response.raise_for_status()
                data = response.json()
                statuses[f"{host_type}"] = extract_status(data)

        except httpx.RequestError as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Error contacting Vespa containers", "details": str(e)},
            )
        except ValueError as e:
            return JSONResponse(
                status_code=500,
                content={"error": "Invalid response structure", "details": str(e)},
            )
        except httpx.HTTPStatusError as e:
            return JSONResponse(
                status_code=e.response.status_code,
                content={"error": "HTTP error", "details": str(e)},
            )

    return JSONResponse(
        status_code=200,
        content=statuses,
    )
