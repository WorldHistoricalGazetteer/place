import errno
import logging
import os
import re
import subprocess
from pprint import pprint

import yaml

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_pv_requirements(
    application: str,
    chart_dir: str,
    values_file: str,
    namespace: str = "default",
    default_uid=1000,
    default_gid=1000,
    default_perms="755"
):
    """Renders a Helm chart and extracts only PV directory requirements (pv_path, uid, gid, perms)."""
    command = [
        "helm", "template", application, chart_dir,
        "--namespace", namespace,
        "-f", values_file
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except Exception as e:
        raise RuntimeError(f"Helm command failed: {e}")

    if result.returncode != 0:
        raise RuntimeError(f"Helm template failed: {result.stderr}")

    rendered_docs = list(yaml.safe_load_all(result.stdout))

    # PV name -> host path
    pv_paths = {}
    for doc in rendered_docs:
        if isinstance(doc, dict) and doc.get("kind") == "PersistentVolume":
            name = doc.get("metadata", {}).get("name")
            spec = doc.get("spec", {})
            path = None
            if "hostPath" in spec:
                path = spec["hostPath"].get("path")
            elif "local" in spec:
                path = spec["local"].get("path")
            if name and path:
                pv_paths[name] = path

    # PVC -> PV mapping
    pvc_to_pv = {}
    for doc in rendered_docs:
        if isinstance(doc, dict) and doc.get("kind") == "PersistentVolumeClaim":
            ns = doc.get("metadata", {}).get("namespace", namespace)
            pvc_name = doc.get("metadata", {}).get("name")
            vol_name = doc.get("spec", {}).get("volumeName")
            if pvc_name and vol_name:
                pvc_to_pv[(ns, pvc_name)] = vol_name

    # Final minimal requirements list
    required_volumes = []
    seen_paths = set()

    for doc in rendered_docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") not in ("Deployment", "StatefulSet", "DaemonSet"):
            continue

        metadata = doc.get("metadata", {})
        ns = metadata.get("namespace", namespace)
        pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
        if not pod_spec:
            continue

        pod_sec_ctx = pod_spec.get("securityContext", {})
        fs_group = pod_sec_ctx.get("fsGroup", default_gid)
        run_as_user = pod_sec_ctx.get("runAsUser", default_uid)

        volumes = pod_spec.get("volumes", [])
        volume_map = {v.get("name"): v for v in volumes}

        for container in pod_spec.get("containers", []):
            container_sec_ctx = container.get("securityContext", {})
            c_run_as_user = container_sec_ctx.get("runAsUser", run_as_user)
            c_fs_group = container_sec_ctx.get("runAsGroup", fs_group)

            for mount in container.get("volumeMounts", []):
                vol = volume_map.get(mount.get("name"), {})
                pvc_ref = vol.get("persistentVolumeClaim")
                if not pvc_ref:
                    continue

                claim_name = pvc_ref.get("claimName")
                if not claim_name:
                    continue

                pv_name = pvc_to_pv.get((ns, claim_name))
                pv_path = pv_paths.get(pv_name) if pv_name else None
                if not pv_path:
                    continue

                if pv_path in seen_paths:
                    continue  # skip duplicates
                seen_paths.add(pv_path)

                required_volumes.append({
                    "pv_path": pv_path,
                    "uid": c_run_as_user,
                    "gid": c_fs_group,
                    "perms": default_perms,
                })

    return required_volumes


def ensure_pv_directories(volumes):
    """Create any missing PV directories and set ownership and permissions."""
    for vol in volumes:
        path = vol["pv_path"]
        uid = vol["uid"]
        gid = vol["gid"]
        perms = int(vol["perms"], 8)

        if not os.path.exists(path):
            try:
                os.makedirs(path, mode=perms, exist_ok=True)
                logger.info(f"Created {path} with perms {vol['perms']}")
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise
        else:
            logger.info(f"{path} already exists")

        try:
            os.chown(path, uid, gid)
            os.chmod(path, perms)
        except PermissionError as e:
            logger.error(f"Permission error on {path}: {e}")