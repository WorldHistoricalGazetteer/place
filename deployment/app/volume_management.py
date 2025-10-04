import errno
import logging
import os
import re
import subprocess
from pprint import pprint

import yaml

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_pv_requirements(application: str, chart_dir: str, values_file: str, namespace: str = "default", default_uid=1000,
                                      default_gid=1000, default_perms="755"):
    """Renders a Helm chart and extracts required volume mount paths and permissions."""
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

    volumes = []
    rendered_docs = list(yaml.safe_load_all(result.stdout))

    # Collect PV name -> path
    pv_paths = {}
    for doc in rendered_docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") == "PersistentVolume":
            name = doc.get("metadata", {}).get("name")
            spec = doc.get("spec", {})
            path = None
            if "hostPath" in spec:
                path = spec["hostPath"].get("path")
            elif "local" in spec:
                path = spec["local"].get("path")
            if name and path:
                pv_paths[name] = path

    # Collect PVC name -> PV name, but only for PVC manifests present (likely only base PVCs)
    pvc_to_pv = {}
    for doc in rendered_docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") == "PersistentVolumeClaim":
            ns = doc.get("metadata", {}).get("namespace", "default")
            pvc_name = doc.get("metadata", {}).get("name")
            vol_name = doc.get("spec", {}).get("volumeName")
            if pvc_name and vol_name:
                pvc_to_pv[(ns, pvc_name)] = vol_name

    # 3. Extract StatefulSet volumeClaimTemplates and securityContext (uid, gid)
    # We'll map (namespace, pvc_template_name) -> {"fs_group": ..., "run_as_user": ...}
    ss_pvc_security = {}
    for doc in rendered_docs:
        if not isinstance(doc, dict):
            continue
        if doc.get("kind") == "StatefulSet":
            metadata = doc.get("metadata", {})
            ns = metadata.get("namespace", namespace)
            pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
            if not pod_spec:
                continue

            pod_sec_ctx = pod_spec.get("securityContext", {})
            fs_group = pod_sec_ctx.get("fsGroup", default_gid)
            run_as_user = pod_sec_ctx.get("runAsUser", default_uid)

            # If containers have securityContext with overrides, use the first container's as example
            containers = pod_spec.get("containers", [])
            if containers:
                container_sec_ctx = containers[0].get("securityContext", {})
                run_as_user = container_sec_ctx.get("runAsUser", run_as_user)
                fs_group = container_sec_ctx.get("runAsGroup", fs_group)

            # Map PVC templates to this security context info
            for vct in doc.get("spec", {}).get("volumeClaimTemplates", []):
                pvc_name = vct.get("metadata", {}).get("name")
                if pvc_name:
                    ss_pvc_security[(ns, pvc_name)] = {
                        "fs_group": fs_group,
                        "run_as_user": run_as_user,
                        "perms": default_perms,
                    }

    # Collect deployment volumes with mount paths and associated PV info
    deployment_volumes = []
    for doc in rendered_docs:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        if kind not in ("Deployment", "StatefulSet", "DaemonSet"):
            continue

        metadata = doc.get("metadata", {})
        ns = metadata.get("namespace", namespace)
        deployment_name = metadata.get("name")
        pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
        if not pod_spec:
            continue

        # Use pod-level securityContext as default
        pod_sec_ctx = pod_spec.get("securityContext", {})
        fs_group = pod_sec_ctx.get("fsGroup", default_gid)
        run_as_user = pod_sec_ctx.get("runAsUser", default_uid)

        volumes = pod_spec.get("volumes", [])
        volume_map = {v.get("name"): v for v in volumes}

        for container in pod_spec.get("containers", []):
            container_name = container.get("name")
            # Container-level securityContext overrides
            container_sec_ctx = container.get("securityContext", {})
            c_run_as_user = container_sec_ctx.get("runAsUser", run_as_user)
            c_fs_group = container_sec_ctx.get("runAsGroup", fs_group)

            for mount in container.get("volumeMounts", []):
                vol_name = mount.get("name")
                mount_path = mount.get("mountPath")

                vol = volume_map.get(vol_name, {})
                pvc_ref = vol.get("persistentVolumeClaim")
                pvc_name = None
                pv_path = None

                if pvc_ref:
                    claim_name = pvc_ref.get("claimName")
                    if claim_name:
                        # Check if claim_name ends with replica suffix, e.g. -0, -1, ...
                        m = re.match(r"^(.*?)-(\d+)$", claim_name)
                        if m:
                            base_pvc_name, idx = m.groups()
                            # Attempt to construct PV name based on replica suffix convention:
                            # This is heuristic: adjust if your naming differs
                            if base_pvc_name.endswith("-pvc"):
                                pv_name_candidate = f"{base_pvc_name[:-4]}-pv-{idx}"
                            else:
                                pv_name_candidate = f"{base_pvc_name}-pv-{idx}"
                            pv_path = pv_paths.get(pv_name_candidate)
                            pvc_name = claim_name  # keep full replica pvc name
                        else:
                            # No replica suffix
                            pvc_name = claim_name
                            vol_name_lookup = pvc_to_pv.get((ns, pvc_name))
                            if vol_name_lookup:
                                pv_path = pv_paths.get(vol_name_lookup)

                deployment_volumes.append({
                    "container": container_name,
                    "deployment_kind": kind,
                    "deployment_name": deployment_name,
                    "namespace": ns,
                    "volume_name": vol_name,
                    "mount_path": mount_path,
                    "perms": default_perms,
                    "uid": c_run_as_user,
                    "gid": c_fs_group,
                    "pv_claim_name": pvc_name,
                    "pv_path": pv_path,
                })

    return pv_paths, pvc_to_pv, ss_pvc_security, deployment_volumes


def ensure_pv_directories(volumes):
    """
    Create any missing PV directories and set ownership and permissions.
    """
    for vol in volumes:
        path = vol["path"]
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
