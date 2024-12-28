import json
import logging
import os

import ijson
import kubernetes
from kubernetes import client
from kubernetes.client import BatchV1Api, V1Job, V1PodSpec, V1PodTemplateSpec, V1ObjectMeta, V1Container, V1Volume, \
    V1VolumeMount, V1PersistentVolumeClaimVolumeSource, V1Affinity
from kubernetes.stream import stream
import time
import requests
import shlex
from typing import Dict, Any
import uuid

# Configure logging
logger = logging.getLogger("tileserver.addition")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)

TILESERVER_HEALTH_URL = "http://tileserver-gl:8080/health"
RESTART_TIMEOUT = 30


def generate_random_suffix() -> str:
    """Generates a random suffix string using UUID."""
    return str(uuid.uuid4().hex[:12])  # First 12 characters for brevity


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


def build_attribution(citation_data: Dict[str, Any]) -> str:
    """
    Build an attribution string from citation data.

    Args:
        citation_data: A dictionary containing citation data.

    Returns:
        str: The attribution string.
    """
    author_names = ", ".join(
        [f"{author.get('given', '')} {author.get('family', '')}".strip()
         if "family" in author else author.get("literal", "Unknown")
         for author in citation_data.get("author", [])]
    )

    attribution_parts = []

    if author_names:
        attribution_parts.append(f"<strong>{author_names}</strong>,")
    attribution_parts.append(f"<em>{citation_data.get('title', 'Unknown')}</em>,")
    attribution_parts.append(f"({citation_data.get('publisher', 'Unknown Publisher')}")
    if citation_data.get("publisher-place"):
        attribution_parts[-1] += f", {citation_data.get('publisher-place')}"
    attribution_parts.append(f" {citation_data.get('issued', {}).get('date-parts', [[]])[0]})")
    if citation_data.get("DOI"):
        attribution_parts.append(f'<a href="https://doi.org/{citation_data["DOI"]}" target="_blank">DOI</a>')
    elif citation_data.get("URL"):
        attribution_parts.append(f'(<a href="{citation_data["URL"]}" target="_blank">link</a>)')

    return " ".join(attribution_parts)


def split_geojson(response, geojson_path, table_path):
    """
    Streams GeoJSON data from a response, saving unmodified features to `tiles_path`
    and reduced features (geometry type only) to `table_path`.

    Args:
        response: HTTP response object containing GeoJSON data.
        geojson_path: Path to save unmodified GeoJSON features for use in tileset generation.
        table_path: Path to save geometry-less features.
    """
    with open(geojson_path, "w") as geojson_file, open(table_path, "w") as table_file:
        # Write headers for both files
        geojson_file.write('{"type": "FeatureCollection", "features": [\n')
        table_file.write('{"features": [\n')

        try:
            logger.info("Streaming GeoJSON data.")
            first_geojson_feature = True
            first_table_feature = True

            for prefix, event, value in ijson.parse(response.raw):
                if prefix == "features.item":
                    if event == "start_map":
                        current_feature = {}
                    elif event == "map_key":
                        current_key = value
                    elif event == "end_map":
                        # Write unmodified feature to tiles_path
                        if not first_geojson_feature:
                            geojson_file.write(",\n")
                        geojson_file.write(json.dumps(current_feature))
                        first_geojson_feature = False

                        # Write reduced feature to table_path
                        if "geometry" in current_feature and current_feature["geometry"]:
                            current_feature["geometry"] = {
                                "type": current_feature["geometry"].get("type")
                            }
                        if not first_table_feature:
                            table_file.write(",\n")
                        table_file.write(json.dumps(current_feature))
                        first_table_feature = False
                    else:
                        # Process current feature data
                        if current_key == "geometry" and event == "start_map":
                            current_feature["geometry"] = {}
                        elif current_key == "geometry" and event == "map_key":
                            geom_key = value
                        elif current_key == "geometry" and event == "string":
                            if geom_key == "type":
                                current_feature["geometry"]["type"] = value
                        else:
                            current_feature[current_key] = value

        except Exception as e:
            raise RuntimeError(f"Failed to process GeoJSON data: {str(e)}")

        # Write footers for both GeoJSON files
        geojson_file.write("\n]}")
        table_file.write("\n]}")


def add_tileset(tileset_type: str, tileset_id: int) -> str:
    """
    Start a Tippecanoe job in Kubernetes to process the tileset.

    Args:
        tileset_type (str): The type of the tileset (e.g., "datasets" or "collections").
        tileset_id (int): The ID of the tileset.

    Returns:
        str: The name of the Job that was created (or an error message if the Job could not be created).

    """

    kubernetes.config.load_incluster_config()

    tiles_mountpath = "/srv/tiles"
    tileserver_mountpath = "/mnt/data"

    namespace = os.getenv("TIPPECANOE_NAMESPACE", "tileserver")
    random_suffix = generate_random_suffix()
    job_name = f"tippecanoe-{tileset_type}-{tileset_id}-{random_suffix}"
    image = f"{os.getenv('TIPPECANOE_IMAGE')}:{os.getenv('TIPPECANOE_IMAGE_TAG')}"
    geojson_url = f"http://django-service.whg.svc.cluster.local:8000/mapdata/{tileset_type}/{tileset_id}/standard/refresh/"
    citation_url = f"http://django-service.whg.svc.cluster.local:8000/{tileset_type}/{tileset_id}/citation"
    restart_url = f"http://tileapi.{namespace}.svc.cluster.local:{os.getenv('PORT')}/restart"

    try:
        geojson_path = f"{tileserver_mountpath}/mapdata/geojson/{tileset_type}/{tileset_id}.geojson"
        os.makedirs(os.path.dirname(geojson_path), exist_ok=True)
        table_path = f"{tileserver_mountpath}/mapdata/tables/{tileset_type}/{tileset_id}.json"
        os.makedirs(os.path.dirname(table_path), exist_ok=True)
    except Exception as e:
        msg = f"Failed to create directories: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)

    # Fetch name and attribution from the citation endpoint
    try:
        citation_response = requests.get(citation_url)
        citation_response.raise_for_status()
        citation_data = citation_response.json()
        name = citation_data.get("title", "-Unknown-")
        attribution = build_attribution(citation_data)
    except requests.RequestException as e:
        msg = f"Failed to fetch citation data: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)
    except Exception as e:
        msg = f"Failed to build attribution string: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)

    # Fetch GeoJSON and create map table data (reduce geometry to type only)
    try:
        logger.info(f"Fetching data from {geojson_url}")
        response = requests.get(geojson_url, stream=True)
        response.raise_for_status()
        split_geojson(response, geojson_path, table_path)
    except requests.RequestException as e:
        msg = f"Failed to fetch GeoJSON data: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)
    except Exception as e:
        msg = f"Failed to process GeoJSON data: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)

    # Construct the Tippecanoe command
    command = " ".join([
        "/tippecanoe/tippecanoe",  # Path to the Tippecanoe binary
        f"-o {tiles_mountpath}/{tileset_type}/{tileset_id}.mbtiles",  # Output file in mounted volume
        "-f",  # Force overwrite output file if it exists
        f"-n {shlex.quote(name)}",  # Name of the tileset
        f"-A {shlex.quote(attribution)}",  # Attribution text
        "-l features",  # Layer name
        "-B 4",  # Buffer size (larger values = more detail but larger tiles)
        "-rg 10",  # Generalization factor (higher = more simplified geometry)
        "-al",  # Enable automatic layering
        "-ap",  # Enable automatic tiling of polygons
        "-z14",  # Set zoom level to 14
        "-ac",  # Allow the creation of tiles for areas with fewer than a certain number of features
        "--no-tile-size-limit",  # Disable tile size limit
        # Feature properties to include (separate flags required for each property)
        "-y=properties.pid",
        "-y=properties.fclasses",
        "-y=properties.relation",
        "-y=properties.min",
        "-y=properties.max",
        f"{shlex.quote(geojson_path)}",
        # Restart the tileserver (triggers rebuild of config.json, incorporating new tileset)
        f"&& curl -sSL {shlex.quote(restart_url)} || echo 'Error restarting tileserver'"
    ]) # Combine the command parts into a single string

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
                    security_context=client.V1PodSecurityContext(
                        fs_group=999,  # Set the group ID for the mounted volume
                    ),
                    containers=[
                        V1Container(
                            name="tippecanoe",
                            image=image,
                            image_pull_policy=os.getenv("TIPPECANOE_IMAGE_PULL_POLICY", "IfNotPresent"),
                            command=["/bin/bash", "-c" , command],
                            volume_mounts=[
                                V1VolumeMount(name="tiles", mount_path=f"{tiles_mountpath}"),
                                V1VolumeMount(name="tileserver", mount_path=f"{tileserver_mountpath}"),
                            ],
                            security_context=client.V1SecurityContext(
                                run_as_user=999,  # Set the user ID to 999
                                run_as_group=999,  # Set the group ID to 999
                            ),
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
