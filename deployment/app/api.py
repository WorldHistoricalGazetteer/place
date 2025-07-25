# deployment/app/api.py

import logging
import os
import subprocess
from contextlib import asynccontextmanager
from typing import Optional, List

import yaml
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel

from volume_management import ensure_pv_directories, get_pv_requirements

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXPECTED_TOKEN = os.getenv("NOTIFY_PITT_TOKEN")


@asynccontextmanager
async def lifespan(app: FastAPI):
    applications_file = "/apps/repository/deployment/applications.yaml"

    if os.path.exists(applications_file):
        with open(applications_file) as f:
            config = yaml.safe_load(f)

        for app_entry in config.get("applications", []):
            name = app_entry.get("name")
            if name:
                logger.info(f"Deploying {name} on startup")
                run_deployment(name)
    else:
        logger.warning(f"No applications.yaml found at {applications_file}")

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/install/{application}")
def install_chart(application: str, namespace: str = "default"):
    """
    For internal use from inside Pitt VM (no other authentication).
    """
    return run_deployment(application, namespace)


class DeployNotification(BaseModel):
    repository: str
    commit: str
    changed_directories: List[str]


@app.post("/deploy")
async def deploy_chart(
        payload: DeployNotification,
        authorization: Optional[str] = Header(None)
):
    """
    Secured endpoint for GitHub Actions.
    """
    if EXPECTED_TOKEN:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
        token = authorization.split(" ", 1)[1]
        if token != EXPECTED_TOKEN:
            raise HTTPException(status_code=403, detail="Invalid token")
    else:
        logger.warning("NOTIFY_PITT_TOKEN not set; skipping token validation")

    logger.info(f"Deploy notification from {payload.repository} at {payload.commit}")
    logger.info(f"Changed directories: {payload.changed_directories}")

    # TODO: Use the application list which is parsed in lifespan
    if "vespa" in payload.changed_directories:
        return run_deployment("vespa", "default")
    else:
        logger.info("No deployment required.")
        return {"status": "ignored", "reason": "no relevant source changed"}


def run_deployment(application: str, namespace: str = "default"):
    application, _, version = application.partition("-")
    suffix = f"-{version}" if version else ""
    path = f"/apps/repository/{application}/values{suffix}.yaml"

    subprocess.run(["git", "-C", path, "pull"], capture_output=True)

    try:
        required_volumes = get_pv_requirements(application, path, namespace)
        if not required_volumes:
            logger.info(f"No required volumes found in {path}")
        else:
            logger.info(f"Required volumes: {required_volumes}")
            ensure_pv_directories(required_volumes)
    except Exception as e:
        return {"status": "error", "message": f"Pre-deployment check failed: {e}"}

    command = f"helm upgrade --install {application} {path} --namespace {namespace}"
    logger.info(f"Running: {command}")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    logger.info(f"Return code: {result.returncode}")
    logger.info(f"STDOUT: {result.stdout}")
    logger.error(f"STDERR: {result.stderr}")

    if result.returncode == 0:
        return {"status": "success", "message": result.stdout}
    else:
        return {"status": "error", "message": result.stderr}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
