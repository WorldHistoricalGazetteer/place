import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen

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

from utils import generate_random_suffix

# Configure logging
logger = logging.getLogger("tileserver.addition")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)
logger.propagate = True

TILESERVER_HEALTH_URL = "http://tileserver-gl:8080/health"
RESTART_TIMEOUT = 60 # seconds
CONFIG_DIR = "/mnt/data/configs"
CONFIG_FILE = Path(CONFIG_DIR) / "config.json"


def restart_tileserver(refresh=True) -> Dict[str, Any]:
    """
    Restarts the tileserver by sending a SIGHUP signal, optionally refreshing the configuration.

    Returns:
        Dict[str, Any]: A dictionary with 'success' and 'message' keys.
    """

    try:
        kubernetes.config.load_incluster_config()

        v1 = client.CoreV1Api()
        v1.api_client.configuration.timeout = RESTART_TIMEOUT # Set the timeout for the API client

        pods = v1.list_namespaced_pod(
            namespace="tileserver",
            label_selector="app=tileserver-gl"
        )

        if not pods.items:
            raise ValueError("No tileserver-gl pod found")

        pod_name = pods.items[0].metadata.name

        command = ["kill", "-HUP", "1"]  # Default command
        if refresh:
            command = [
                "ls -la /opt/reconfiguration/ /mnt/data/configs/ &&",
                "/usr/bin/node",
                "/opt/reconfiguration/merge-config.js",
                "/opt/reconfiguration/base-config.json",
                "/mnt/data/configs/config.json",
                "/mnt/data/tiles > /proc/1/fd/1 2>/proc/1/fd/2",
                "&&",
            ] + command

        api_instance = kubernetes.client.CoreV1Api()
        response = stream(
            api_instance.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace="tileserver",
            container="tileserver-gl",
            command=["sh", "-c", " ".join(command)],
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
        attribution_parts.append(f"{author_names},")
    attribution_parts.append(f"<strong><em>{citation_data.get('title', 'Unknown')}</em></strong>,")
    attribution_parts.append(f"({citation_data.get('publisher', 'Unknown Publisher')}")
    # if citation_data.get("publisher-place"):
    #     attribution_parts[-1] += f", {citation_data.get('publisher-place')}"
    publication_year = citation_data.get('issued', {}).get('date-parts', [[None]])[0][0]
    attribution_parts.append(f" {publication_year})" if publication_year else ")")
    if citation_data.get("DOI"):
        attribution_parts.append(f'<a href="https://doi.org/{citation_data["DOI"]}" target="_blank">doi:{citation_data["DOI"]}</a>')
    elif citation_data.get("URL"):
        attribution_parts.append(f'(<a href="{citation_data["URL"]}" target="_blank">link</a>)')

    return " ".join(attribution_parts)


def decimal_default(obj):
    """
    Custom serialization for Decimal types.
    Converts Decimal to float for JSON serialization.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {obj.__class__.__name__} not serializable")


def split_geojson(f, geojson_path, table_path):
    """
    Streams GeoJSON data from a file, saving unmodified features to `geojson_path`
    and reduced features (geometry type only) to `table_path`.

    Args:
        f: File-like object containing GeoJSON data.
        geojson_path: Path to save unmodified GeoJSON features for use in tileset generation.
        table_path: Path to save geometry-less features.
    """
    try:
        with open(geojson_path, "w") as geojson_file, open(table_path, "w") as table_file:
            # Write headers for both files
            geojson_file.write('{"type": "FeatureCollection", "features": [\n')
            table_file.write('{"features": [\n')

            logger.info("Streaming GeoJSON data.")
            first_geojson_feature = True
            first_table_feature = True

            features = ijson.items(f, "features.item")
            for feature in features:
                # Write unmodified feature to geojson_path
                if not first_geojson_feature:
                    geojson_file.write(",\n")
                geojson_file.write(json.dumps(feature, default=decimal_default))
                first_geojson_feature = False

                # Process and write reduced feature to table_path
                if "geometry" in feature and feature["geometry"]:
                    feature["geometry"] = {"type": feature["geometry"].get("type")}
                if not first_table_feature:
                    table_file.write(",\n")
                table_file.write(json.dumps(feature, default=decimal_default))
                first_table_feature = False

    except ijson.common.JSONError as e:
        logger.error(f"JSON parsing error: {e}")
        raise RuntimeError(f"Failed to process GeoJSON data: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise RuntimeError(f"Failed to process GeoJSON data: {str(e)}")
    finally:
        # Ensure file footers are written even in case of error
        with open(geojson_path, "a") as geojson_file, open(table_path, "a") as table_file:
            geojson_file.write("\n]}")
            table_file.write("\n]}")


def wipe_config(tileset_key):
    """
    Wipe any pre-existing entry from the configuration file.
    """
    try:
        with CONFIG_FILE.open("r") as f:
            config = json.load(f)

        # Remove the tileset entry from the config if it exists
        tilesets = config.get("data", {})
        if tileset_key in tilesets:
            try:
                del tilesets[tileset_key]
                logger.info(f"Removed tileset '{tileset_key}' from configuration.")
            except Exception as e:
                message = f"Failed to remove tileset '{tileset_key}' from configuration: {str(e)}"
                logger.error(message)
                raise RuntimeError(message)
        else:
            message = f"Tileset key '{tileset_key}' not found in configuration."
            logger.info(message)
            return

        # Save the updated configuration back to the file
        try:
            with CONFIG_FILE.open("w") as f:
                json.dump(config, f, indent=4)
            logger.info(f"Updated configuration file: {CONFIG_FILE}")
        except Exception as e:
            message = f"Failed to update configuration file: {str(e)}"
            logger.error(message)
            raise RuntimeError(message)
    except FileNotFoundError:
        message = "Configuration file not found."
        logger.error(message)
        raise RuntimeError(message)


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
    geojson_url = f"http://django-service.whg.svc.cluster.local:8000/mapdata/{tileset_type}/{tileset_id}/refresh/full/"
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
        logger.info(f"Fetched citation data: {citation_data}")
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
        f = urlopen(geojson_url)
        split_geojson(f, geojson_path, table_path)
    except Exception as e:
        msg = f"Failed to process GeoJSON data: {str(e)}"
        logger.error(msg)
        raise RuntimeError(msg)

    # Remove any pre-existing entry from the config.json file
    wipe_config(f"{tileset_type}-{tileset_id}")

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
