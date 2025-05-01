from fastapi import FastAPI
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/install/{chart_name}")
def install_chart(chart_name: str, namespace: str = "default"):
    # TODO: This is as yet only a prototype. See Issue
    command = f"helm install {chart_name} /apps/repository/{chart_name} --namespace {namespace}"
    logger.info(f"Running command: {command}")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    logger.info(f"Return code: {result.returncode}")
    logger.info(f"STDOUT: {result.stdout}")
    logger.error(f"STDERR: {result.stderr}")

    if result.returncode == 0:
        return {"status": "success", "message": result.stdout}
    else:
        return {"status": "error", "message": result.stderr}

if __name__ == "__main__":
    logger.info("Starting FastAPI server...")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)