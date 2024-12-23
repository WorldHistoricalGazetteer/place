import kubernetes
from kubernetes.client import BatchV1Api, V1Job
from kubernetes.stream import stream
import time
import requests
from typing import Dict, Any

TILESERVER_HEALTH_URL = "http://tileserver-gl:8080/health"
RESTART_TIMEOUT = 30

def restart_tileserver() -> Dict[str, Any]:
    """
    Restarts the tileserver by sending a SIGHUP signal.

    Returns:
        Dict[str, Any]: A dictionary with 'success' and 'message' keys.
    """
    try:
        kubernetes.config.load_incluster_config()

        api_instance = kubernetes.client.CoreV1Api()
        response = stream(
            api_instance.connect_get_namespaced_pod_exec,
            name="tileserver-gl",
            namespace="tileserver",
            container="tileserver-gl",
            command=["kill", "-HUP", "1"],
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
        )
        # Poll the health endpoint
        start_time = time.time()
        while time.time() - start_time < RESTART_TIMEOUT:
            try:
                health_response = requests.get(TILESERVER_HEALTH_URL, timeout=5)
                if health_response.status_code == 200:
                    return {"success": True, "message": "Tileserver restarted successfully."}
            except requests.RequestException:
                pass  # Ignore errors and keep polling
            time.sleep(1)
        return {"success": True, "message": f"Restart command executed successfully: {response}"}
    except kubernetes.client.exceptions.ApiException as e:
        return {"success": False, "message": f"API Exception when restarting tileserver: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error occurred: {e}"}


def start_tippecanoe_job(tileset_type: str, tileset_id: int, geojson_url: str , name: str, attribution: str) -> str:
    """
    Start a Tippecanoe job in Kubernetes to process the tileset using a preloaded job as a template.

    Args:
        tileset_type (str): The type of tileset (e.g., "dataset" or "collection").
        tileset_id (int): The identifier of the dataset or collection.
        geojson (dict): The GeoJSON data to be processed.
        name (str): The name of the tileset (used in metadata).
        attribution (str): The attribution text (used in metadata).

    Returns:
        str: Job ID of the Tippecanoe operation.
    """

    kubernetes.config.load_incluster_config()

    # Fetch data from the geojson_url and save it to a temporary file
    try:
        response = requests.get(geojson_url, stream=True)
        response.raise_for_status()
        with open("/tmp/geojson.json", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch GeoJSON data from {geojson_url}: {str(e)}")

    api_instance = BatchV1Api()
    template_job_name = "tippecanoe-job"
    namespace = "tileserver"

    # Fetch the preloaded Job template (this method allows for Helm-based job configuration from `values.yaml`)
    try:
        template_job: V1Job = api_instance.read_namespaced_job(name=template_job_name, namespace=namespace)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch template Job '{template_job_name}': {str(e)}")

    # Modify the fetched Job's metadata and args
    job_name = f"tippecanoe-{tileset_type}-{tileset_id}"
    job_manifest = template_job.to_dict()
    job_manifest["metadata"]["name"] = job_name
    job_manifest["metadata"].pop("uid", None)
    job_manifest["metadata"].pop("resourceVersion", None)

    # Modify the args for the container
    job_manifest["spec"]["template"]["spec"]["containers"][0]["args"] = [
        "/tippecanoe/tippecanoe",  # Path to the Tippecanoe binary
        "-o", f"{tileset_type}-{tileset_id}.mbtiles",  # Output file name
        "-f",  # Force overwrite output file if it exists
        "-n", name,  # Name of the tileset
        "-A", attribution,  # Attribution text
        "-l", "features",  # Layer name
        "-B", "4",  # Buffer size (larger values = more detail but larger tiles)
        "-rg", "10",  # Generalization factor (higher = more simplified geometry)
        "-al",  # Enable automatic layering
        "-ap",  # Enable automatic tiling of polygons
        "-z14",  # Set zoom level to 14
        "-ac",  # Allow the creation of tiles for areas with fewer than a certain number of features
        "--no-tile-size-limit",  # Disable tile size limit
        "/tmp/geojson.json",  # Path to the GeoJSON input file
    ]

    # Submit the modified Job
    try:
        api_instance.create_namespaced_job(namespace=namespace, body=job_manifest)
        return job_name
    except Exception as e:
        raise RuntimeError(f"Failed to create Tippecanoe job '{job_name}': {str(e)}")
