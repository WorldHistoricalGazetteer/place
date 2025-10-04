# deployment/app/api.py

import logging
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from pprint import pprint
from typing import Optional, List

import yaml
from fastapi import FastAPI, Request, Header, HTTPException, Query
from pydantic import BaseModel

from volume_management import ensure_pv_directories, get_pv_requirements

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

GITHUB_REPO = "https://github.com/WorldHistoricalGazetteer/place.git"
CLONE_ROOT = "/apps/repository"


def get_applications(check_exists = None):
    """
    Reads the applications.yaml file and returns a list of application names.
    """
    applications_file = f"{CLONE_ROOT}/deployment/applications.yaml"
    if not os.path.exists(applications_file):
        logger.warning(f"No applications.yaml found at {applications_file}")
        return []

    with open(applications_file) as f:
        config = yaml.safe_load(f)

    applications = config.get("applications", [])

    if check_exists:
        return any(app.get("name") == check_exists for app in applications)

    return [app.get("name") for app in applications if app.get("name")]


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
    if not get_applications(check_exists=application):
        return {"status": "error", "message": f"Application {application} not found in applications.yaml"}

    return run_deployment(application, namespace)


@app.post("/rollback")
def rollback_chart(
        application: str,
        revision: Optional[int] = Query(None, description="Revision number to roll back to"),
        namespace: str = "default"
):
    """
    Roll back a Helm release to a previous revision.
    """
    if not get_applications(check_exists=application):
        return {"status": "error", "message": f"Application {application} not found in applications.yaml"}

    command = ["helm", "rollback", application]
    if revision:
        command.append(str(revision))
    command.extend(["--namespace", namespace])

    logger.info(f"Rolling back {application} in namespace {namespace} "
                f"{f'to revision {revision}' if revision else '(to previous revision)'}")

    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except Exception as e:
        logger.error(f"Helm rollback command failed: {e}")
        return {"status": "error", "message": str(e)}

    logger.info(f"Return code: {result.returncode}")
    logger.info(f"STDOUT: {result.stdout}")
    logger.error(f"STDERR: {result.stderr}")

    if result.returncode == 0:
        return {"status": "success", "message": result.stdout}
    else:
        return {"status": "error", "message": result.stderr}


class DeployNotification(BaseModel):
    repository: str
    commit: str
    changed_directories: List[str]


# @app.post("/deploy")
# async def deploy_chart(
#         payload: DeployNotification,
#         authorization: Optional[str] = Header(None)
# ):
#     # TODO: This endpoint was developed for use with GitHUb Action-based CI/CD, and may not be required for ArgoCD-based deployments.
#
#     logger.info(f"Deploy notification from {payload.repository} at {payload.commit}")
#     logger.info(f"Changed directories: {payload.changed_directories}")
#
#     predeployed_applications = get_applications()
#     changed_apps = set(predeployed_applications) & set(payload.changed_directories)
#
#     if not changed_apps:
#         logger.info("No deployed applications changed; skipping re-deployment.")
#         return {"status": "skipped", "message": "No matching deployed applications were modified."}
#
#     # Log the applications that will be deployed
#     logger.info(f"Applications to deploy: {changed_apps}")
#
#     for app in changed_apps:
#         logger.info(f"Deploying {app} due to changes in {payload.changed_directories}")
#         result = run_deployment(app)
#         if result.get("status") != "success":
#             logger.error(f"Deployment failed for {app}: {result.get('message')}")
#         else:
#             logger.info(f"Deployment succeeded for {app}: {result.get('message')}")


def pull_application_directory(application: str):
    repo_path = os.path.join(CLONE_ROOT, application)

    if os.path.exists(repo_path):
        logger.info(f"Removing existing directory at {repo_path}")
        shutil.rmtree(repo_path)

    os.makedirs(CLONE_ROOT, exist_ok=True)

    try:
        subprocess.run([
            "git", "clone",
            "--depth", "1",
            "--filter=blob:none",
            "--sparse",
            GITHUB_REPO,
            application
        ], cwd=CLONE_ROOT, check=True)

        subprocess.run([
            "git", "-C", application, "sparse-checkout", "set", f"{application}/"
        ], cwd=CLONE_ROOT, check=True)

        logger.info(f"Successfully pulled {application}/ into {repo_path}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git sparse clone failed: {e.stderr or e.stdout}")


def run_deployment(application: str, namespace: str = "default") -> dict:
    application, _, version = application.partition("-")

    try:
        pull_application_directory(application)
    except Exception as e:
        return {"status": "error", "message": f"Git pull failed: {e}"}

    chart_dir = f"{CLONE_ROOT}/{application}/{application}"  # Git duplicates name in path
    suffix = f"-{version}" if version else ""
    values_file = f"{chart_dir}/values{suffix}.yaml"

    try:
        logger.info(f"Getting PV requirements for {application} from {values_file} in namespace {namespace}")
        required_volumes = get_pv_requirements(application, chart_dir, values_file, namespace)


        if not required_volumes:
            logger.info(f"No required volumes found in {values_file}")
        else:
            logger.info(f"Ensuring required PV directories exist: {required_volumes}")
            ensure_pv_directories(required_volumes)
    except Exception as e:
        logger.error(f"Pre-deployment volume check failed: {e}")
        return {"status": "error", "message": f"Pre-deployment check failed: {e}"}

    command = f"helm upgrade --install {application} {chart_dir} -f {values_file} --namespace {namespace}"
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
