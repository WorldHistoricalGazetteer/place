import logging
import os
import shlex

import kubernetes
from kubernetes import client
from kubernetes.client import BatchV1Api, V1Job, V1PodSpec, V1PodTemplateSpec, V1ObjectMeta, V1Container, V1Volume, \
    V1VolumeMount, V1PersistentVolumeClaimVolumeSource, V1Affinity

from .utils import generate_random_suffix

# Configure logging
logger = logging.getLogger("tileserver.addition")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)
logger.propagate = True


def natural_earth_tileset():
    """
    Start a Tippecanoe job in Kubernetes to process the tileset.
    
    Returns:
        str: The name of the Job that was created (or an error message if the Job could not be created).
    """
    # kubernetes.config.load_incluster_config()
    kubernetes.config.load_kube_config("/home/stephen/.kube/config-pycharm")

    tiles_mountpath = "/srv/tiles"
    tileserver_mountpath = "/mnt/data"

    namespace = os.getenv("TIPPECANOE_NAMESPACE", "tileserver")
    random_suffix = generate_random_suffix()
    job_name = f"tippecanoe-natural-earth-{random_suffix}"
    image = f"{os.getenv('TIPPECANOE_IMAGE', 'worldhistoricalgazetteer/tippecanoe')}:{os.getenv('TIPPECANOE_IMAGE_TAG', 'v0.0.2')}"
    restart_url = f"http://tileapi.{namespace}.svc.cluster.local:{os.getenv('PORT', '30081')}/restart"

    # Define output layers (this mirrors the Bash script's layerset)
    output_layers = [
        ("ne_10m_rivers_lake_centerlines", "-Z0", "-z7", "rivers"),
        ("ne_10m_lakes", "-Z0", "-z7", "lakes"),
        ("ne_10m_ocean", "-Z0", "-z7", "ocean"),
        ("ne_10m_antarctic_ice_shelves_polys", "-Z0", "-z7", "ice"),
        ("ne_10m_geography_regions_polys_labels", "-Z0", "-z2", "regions_labels"),
        ("ne_10m_admin_0_countries", "-Z1", "-z6", "countries"),
        ("ne_10m_admin_0_countries_labels", "-Z1", "-z6", "countries_labels"),
        ("ne_10m_admin_1_states_provinces", "-Z3", "-z7", "states"),
        ("ne_10m_admin_1_states_provinces_labels", "-Z3", "-z7", "states_labels"),
        ("ne_10m_admin_2_counties", "-Z5", "-z7", "counties"),
        ("ne_10m_populated_places", "-Z7", "-z7", "settlements")
    ]
    output_filename = "whg-ne-basic"
    output_description = "Natural Earth: Water, Ice, Regions, Countries, States, Counties, Settlements"
    output_attribution = "<a href=\"https://www.naturalearthdata.com/\" target=\"_blank\">&copy; Natural Earth</a>"


    temp_dir = f"{tileserver_mountpath}/tmp/tippecanoe-{random_suffix}" # Directory for intermediate files
    commands = [f"mkdir -p {temp_dir}"]
    commands.append(f"ls -la {tileserver_mountpath}/data/natural-earth/geojson") # Debugging
    output_files = []

    for layer, zoom_min, zoom_max, layer_name in output_layers:
        geojson_file = f"{tileserver_mountpath}/data/natural-earth/geojson/{layer}.geojson"
        mbtiles_file = f"{temp_dir}/{layer}.mbtiles"
        output_files.append(shlex.quote(mbtiles_file))

        # Check if "zg" is present in zoom args
        extend_zooms = " --extend-zooms-if-still-dropping" if "zg" in (zoom_min, zoom_max) else ""

        tippecanoe_cmd = f"/tippecanoe/tippecanoe {zoom_min} {zoom_max}{extend_zooms} -o {mbtiles_file} --coalesce-densest-as-needed --layer={layer_name} {shlex.quote(geojson_file)}"
        logger.info(f"Queuing: {tippecanoe_cmd}")
        commands.append(tippecanoe_cmd)

    output_filepath = f"{tiles_mountpath}/{output_filename}.mbtiles"
    tilejoin_cmd = f"/tippecanoe/tile-join --no-tile-size-limit -o {shlex.quote(output_filepath)} -A {shlex.quote(output_attribution)} -n {shlex.quote(output_filename)} -N {shlex.quote(output_description)} --force {' '.join(output_files)}"
    commands.append(tilejoin_cmd)

    commands.append(f"rm -r {temp_dir}") # Clean up intermediate files
    commands.append(f"curl -sSL {shlex.quote(restart_url)} || echo 'Error restarting tileserver'") # Restart the tileserver

    # Construct the Job command
    command = " && ".join(commands)

    logger.info(f"Creating Tippecanoe Job '{job_name}' in namespace '{namespace}'")
    logger.info(f"Command: {command}")

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
                            command=["/bin/bash", "-c", command],
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
                    restart_policy="Never",  # Do not restart the Job if it fails
                ),
            ),
            backoffLimit=4,  # Retry the Job up to 4 times
            ttlSecondsAfterFinished=3600,  # Automatically clean up the Job after 1 hour
        ),
    )

    # Submit the Job to Kubernetes
    api_instance = BatchV1Api()
    try:
        api_instance.create_namespaced_job(namespace=namespace, body=job_manifest)
        return job_name
    except Exception as e:
        raise RuntimeError(f"Failed to create Tippecanoe job '{job_name}': {str(e)}")

natural_earth_tileset()