# deployment/app/api.py

import logging
import os
import shutil
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
GITHUB_REPO = "https://github.com/WorldHistoricalGazetteer/place.git"
CLONE_ROOT = "/apps/repository"


def get_applications():
    """
    Reads the applications.yaml file and returns a list of application names.
    """
    applications_file = "/apps/repository/deployment/applications.yaml"
    if not os.path.exists(applications_file):
        logger.warning(f"No applications.yaml found at {applications_file}")
        return []

    with open(applications_file) as f:
        config = yaml.safe_load(f)

    return [app.get("name") for app in config.get("applications", []) if app.get("name")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan handler that deploys all applications defined in applications.yaml at startup.
    """
    application_names = get_applications()

    if not application_names:
        logger.warning("No applications to deploy at startup.")
    else:
        for name in application_names:
            logger.info(f"Deploying {name} on startup")
            run_deployment(name)

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

    predeployed_applications = get_applications()
    changed_apps = set(predeployed_applications) & set(payload.changed_directories)

    if not changed_apps:
        logger.info("No deployed applications changed; skipping re-deployment.")

    # Log the applications that will be deployed
    logger.info(f"Applications to deploy: {changed_apps}")

    for app in changed_apps:
        logger.info(f"Deploying {app} due to changes in {payload.changed_directories}")
        result = run_deployment(app)
        if result.get("status") != "success":
            logger.error(f"Deployment failed for {app}: {result.get('message')}")
        else:
            logger.info(f"Deployment succeeded for {app}: {result.get('message')}")


def pull_application_directory(application: str):
    repo_path = os.path.join(CLONE_ROOT, application)

    if os.path.exists(repo_path):
        logger.info(f"Removing existing directory at {repo_path}")
        shutil.rmtree(repo_path)

    os.makedirs(CLONE_ROOT, exist_ok=True)

    # Use sparse checkout to pull just the required directory
    cmds = [
        ["git", "init", application],
        ["git", "-C", application, "remote", "add", "-f", "origin", GITHUB_REPO],
        ["git", "-C", application, "config", "core.sparseCheckout", "true"],
        ["bash", "-c", f"echo '{application}/*' > {application}/.git/info/sparse-checkout"],
        ["git", "-C", application, "pull", "origin", "main"],
    ]

    for cmd in cmds:
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=CLONE_ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")

    logger.info(f"Successfully pulled application directory: {application}")


def run_deployment(application: str, namespace: str = "default"):
    application, _, version = application.partition("-")

    try:
        pull_application_directory(application)
    except Exception as e:
        return {"status": "error", "message": f"Git pull failed: {e}"}

    suffix = f"-{version}" if version else ""
    path = f"/apps/repository/{application}/values{suffix}.yaml"

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
