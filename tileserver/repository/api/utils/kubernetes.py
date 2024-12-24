import os
import kubernetes
from kubernetes import client
from kubernetes.client import BatchV1Api, V1Job, V1PodSpec, V1PodTemplateSpec, V1ObjectMeta, V1Container, V1Volume, \
    V1VolumeMount, V1PersistentVolumeClaimVolumeSource, V1Affinity
from kubernetes.stream import stream
import time
import requests
import shlex
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

        v1 = client.CoreV1Api()

        pods = v1.list_namespaced_pod(
            namespace="tileserver",
            label_selector="app=tileserver-gl"
        )

        if not pods.items:
            raise ValueError("No tileserver-gl pod found")

        pod_name = pods.items[0].metadata.name

        api_instance = kubernetes.client.CoreV1Api()
        response = stream(
            api_instance.connect_get_namespaced_pod_exec,
            name=pod_name,
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
    except Exception as e:
        return {"success": False, "message": f"Error restarting tileserver: {e}"}


def start_tippecanoe_job(tileset_type: str, tileset_id: int, geojson_url: str, name: str, attribution: str) -> str:
    """
    Start a Tippecanoe job in Kubernetes to process the tileset using a preloaded job as a template.

    Args:
        tileset_type (str): The type of the tileset (e.g., "datasets" or "collections").
        tileset_id (int): The ID of the tileset.
        geojson_url (str): The URL of the GeoJSON data to process.
        name (str): The name of the tileset.
        attribution (str): The attribution text for the tileset.

    Returns:
        str: The name of the Job that was created (or an error message if the Job could not be created).

    """

    kubernetes.config.load_incluster_config()

    # Create an emptyDir volume for sharing GeoJSON file
    volume_name = "geojson-volume"
    volume_mount_path = "/mnt/geojson"

    # Fetch data from the geojson_url and save it to a temporary file
    try:
        response = requests.get(geojson_url, stream=True)
        response.raise_for_status()
        with open(f"{volume_mount_path}/geojson.json", "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch GeoJSON data from {geojson_url}: {str(e)}")

    namespace = os.getenv("TIPPECANOE_NAMESPACE", "tileserver")
    job_name = f"tippecanoe-{tileset_type}-{tileset_id}"
    image = f"{os.getenv('TIPPECANOE_IMAGE')}:{os.getenv('TIPPECANOE_IMAGE_TAG')}"

    args = [
        "/tippecanoe/tippecanoe",  # Path to the Tippecanoe binary
        "-o", f"{tileset_type}-{tileset_id}.mbtiles",  # Output file name
        "-f",  # Force overwrite output file if it exists
        "-n", shlex.quote(name),  # Name of the tileset
        "-A", shlex.quote(attribution),  # Attribution text
        "-l", "features",  # Layer name
        "-B", "4",  # Buffer size (larger values = more detail but larger tiles)
        "-rg", "10",  # Generalization factor (higher = more simplified geometry)
        "-al",  # Enable automatic layering
        "-ap",  # Enable automatic tiling of polygons
        "-z14",  # Set zoom level to 14
        "-ac",  # Allow the creation of tiles for areas with fewer than a certain number of features
        "--no-tile-size-limit",  # Disable tile size limit
        f"{volume_mount_path}/geojson.json",  # Path to the GeoJSON input file
    ]

    job_manifest = V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=V1ObjectMeta(name=job_name, namespace=namespace),
        spec=dict(
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels={"app": "tippecanoe-job"}),
                spec=V1PodSpec(
                    affinity=V1Affinity(
                        node_affinity=dict(
                            requiredDuringSchedulingIgnoredDuringExecution=dict(
                                nodeSelectorTerms=[
                                    dict(
                                        matchExpressions=[
                                            dict(key="tileserver", operator="In", values=["true"])
                                        ]
                                    )
                                ]
                            )
                        )
                    ),
                    containers=[
                        V1Container(
                            name="tippecanoe",
                            image=image,
                            image_pull_policy=os.getenv("TIPPECANOE_IMAGE_PULL_POLICY"),
                            command=["/bin/bash", "-c"],
                            args=[" ".join(args)],
                            volume_mounts=[
                                V1VolumeMount(name="tiles", mount_path="/srv/tiles"),
                                V1VolumeMount(name="tileserver", mount_path=volume_mount_path),
                            ],
                        )
                    ],
                    volumes=[
                        V1Volume(
                            name="tiles",
                            persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name="tiles-pvc"),
                        ),
                        V1Volume(
                            name="tileserver",
                            persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name="tileserver-pvc"),
                        ),
                    ],
                    restart_policy="Never", # Do not restart the Job if it fails
                ),
            ),
            backoffLimit=4, # Retry the Job up to 4 times
            ttlSecondsAfterFinished=3600, # Automatically clean up the Job after 1 hour
        ),
    )

    # Submit the Job to Kubernetes
    api_instance = BatchV1Api()
    try:
        api_instance.create_namespaced_job(namespace=namespace, body=job_manifest)
        return job_name
    except Exception as e:
        raise RuntimeError(f"Failed to create Tippecanoe job '{job_name}': {str(e)}")
