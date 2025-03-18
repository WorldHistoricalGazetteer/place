from fastapi import FastAPI
import subprocess

app = FastAPI()

@app.get("/install/{chart_name}")
def install_chart(chart_name: str, namespace: str = "default"):
    command = f"helm install {chart_name} /apps/repository/{chart_name} --namespace {namespace}"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        return {"status": "success", "message": result.stdout}
    else:
        return {"status": "error", "message": result.stderr}

