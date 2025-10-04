import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PV_MOUNT_ROOT = os.environ.get("PV_MOUNT_ROOT", "/ix1/whcdh")

REMOTE_CONFIG = {
    "main_host": {
        "host": "144.126.204.70",
        "user": "whgadmin",
        "secret_key": "id_rsa_whg"
    },
    "tiler_host": {
        "host": "134.209.177.234",
        "user": "whgadmin",
        "secret_key": "id_rsa"
    }
}

SYNC_PATHS = {
    "whg": [
        {
            "remote": "/home/whgadmin/sites/whgazetteer-org/media",
            "local": f"{PV_MOUNT_ROOT}/django-media",
            "host": "main_host"
        },
        {
            "remote": "/home/whgadmin/sites/whgazetteer-org/static",
            "local": f"{PV_MOUNT_ROOT}/django-static",
            "host": "main_host"
        }
    ],
    "tileserver": [
        {
            "remote": "/srv/tileserver/configs",
            "local": f"{PV_MOUNT_ROOT}/tileserver/configs",
            "host": "tiler_host"
        },
        {
            "remote": "/srv/tileserver/tiles",
            "local": f"{PV_MOUNT_ROOT}/tiles",
            "host": "tiler_host"
        }
    ]
}

BACKUP_CONFIG = {
    "remote_dir": "/home/whgadmin/backup/whgazetteer-org",
    "local_dir": f"{PV_MOUNT_ROOT}/postgres",
    "host": "main_host"
}


def get_ssh_key_from_secret(key_name: str, namespace: str = "whg") -> Optional[str]:
    """
    Extract SSH key from Kubernetes secret and save to temp file.
    Returns path to the key file.
    """
    try:
        result = subprocess.run(
            ["kubectl", "get", "secret", "whg-secret", "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )

        import json
        import base64

        secret_data = json.loads(result.stdout)
        key_b64 = secret_data.get("data", {}).get(key_name)

        if not key_b64:
            logger.error(f"Key {key_name} not found in secret")
            return None

        key_content = base64.b64decode(key_b64).decode('utf-8')

        # Create temp file for key
        fd, key_path = tempfile.mkstemp(suffix='.pem')
        os.write(fd, key_content.encode('utf-8'))
        os.close(fd)
        os.chmod(key_path, 0o600)

        return key_path

    except Exception as e:
        logger.error(f"Failed to extract SSH key: {e}")
        return None


def rsync_directory(remote_path: str, local_path: str, ssh_key: str,
                    remote_user: str, remote_host: str) -> bool:
    """
    Rsync a directory from remote host to local path.
    """
    try:
        # Ensure local directory exists
        Path(local_path).mkdir(parents=True, exist_ok=True)

        remote_source = f"{remote_user}@{remote_host}:{remote_path}/"

        command = [
            "rsync",
            "-avz",
            "--delete",  # Remove files that don't exist on remote
            "-e", f"ssh -i {ssh_key} -o StrictHostKeyChecking=no",
            remote_source,
            local_path
        ]

        logger.info(f"Syncing {remote_source} to {local_path}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )

        if result.returncode == 0:
            logger.info(f"Successfully synced {remote_path}")
            return True
        else:
            logger.error(f"Rsync failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Rsync timeout for {remote_path}")
        return False
    except Exception as e:
        logger.error(f"Rsync error: {e}")
        return False


def fetch_latest_backup(ssh_key: str, remote_user: str, remote_host: str,
                        remote_backup_dir: str, local_database_dir: str) -> bool:
    """
    Fetch and extract the latest database backup from remote host.
    """
    try:
        # Find latest backup file
        find_cmd = f"ls -t {remote_backup_dir}/*.tar.gz | head -n 1"
        ssh_cmd = [
            "ssh",
            "-i", ssh_key,
            "-o", "StrictHostKeyChecking=no",
            f"{remote_user}@{remote_host}",
            find_cmd
        ]

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
        latest_backup = result.stdout.strip()

        if not latest_backup:
            logger.error("No backup files found")
            return False

        logger.info(f"Found latest backup: {latest_backup}")

        # Fetch backup file
        backup_filename = os.path.basename(latest_backup)
        local_backup_path = os.path.join(local_database_dir, backup_filename)

        rsync_cmd = [
            "rsync",
            "-avz",
            "-e", f"ssh -i {ssh_key} -o StrictHostKeyChecking=no",
            f"{remote_user}@{remote_host}:{latest_backup}",
            local_backup_path
        ]

        logger.info(f"Fetching backup file...")
        result = subprocess.run(rsync_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to fetch backup: {result.stderr}")
            return False

        # Extract backup
        logger.info(f"Extracting backup...")
        tar_cmd = ["tar", "-xzf", local_backup_path, "-C", local_database_dir]
        result = subprocess.run(tar_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to extract backup: {result.stderr}")
            return False

        # Cleanup
        os.remove(local_backup_path)

        # Fix permissions
        subprocess.run(["chown", "-R", "999:999", local_database_dir])
        subprocess.run(["chmod", "-R", "700", local_database_dir])

        logger.info("Database backup successfully restored")
        return True

    except Exception as e:
        logger.error(f"Backup fetch failed: {e}")
        return False


def restore_database_backup(namespace: str = "whg") -> Dict[str, str]:
    """
    Fetch and restore the latest database backup.
    """
    host_config = REMOTE_CONFIG[BACKUP_CONFIG["host"]]

    ssh_key = get_ssh_key_from_secret(host_config["secret_key"], namespace)
    if not ssh_key:
        return {"status": "error", "message": "Failed to get SSH key"}

    try:
        success = fetch_latest_backup(
            ssh_key,
            host_config["user"],
            host_config["host"],
            BACKUP_CONFIG["remote_dir"],
            BACKUP_CONFIG["local_dir"]
        )

        return {
            "status": "success" if success else "error",
            "message": "Database restored" if success else "Failed to restore database"
        }
    finally:
        if os.path.exists(ssh_key):
            os.remove(ssh_key)


def sync_resource(application: str, namespace: str = "whg") -> Dict[str, str]:
    """
    Sync all resources for a specific application.
    """
    if application not in SYNC_PATHS:
        logger.info(f"No remote sync required for {application}")
        return {"status": "skipped", "message": f"No sync configuration for {application}"}

    configs = SYNC_PATHS[application]
    results = []
    ssh_keys = {}  # Cache SSH keys by secret name

    try:
        for config in configs:
            host_config = REMOTE_CONFIG[config["host"]]
            secret_key_name = host_config["secret_key"]

            # Get SSH key (cached if already retrieved)
            if secret_key_name not in ssh_keys:
                ssh_key = get_ssh_key_from_secret(secret_key_name, namespace)
                if not ssh_key:
                    return {"status": "error", "message": f"Failed to get SSH key: {secret_key_name}"}
                ssh_keys[secret_key_name] = ssh_key
            else:
                ssh_key = ssh_keys[secret_key_name]

            success = rsync_directory(
                config["remote"],
                config["local"],
                ssh_key,
                host_config["user"],
                host_config["host"]
            )

            results.append({
                "path": config["remote"],
                "success": success
            })

        # Check if all syncs succeeded
        all_success = all(r["success"] for r in results)
        failed = [r["path"] for r in results if not r["success"]]

        if application == "whg" and all_success:
            postgres_dir = BACKUP_CONFIG["local_dir"]

            # Check if postgres directory is empty or doesn't exist
            needs_restore = (
                    not os.path.exists(postgres_dir) or
                    len(os.listdir(postgres_dir)) == 0
            )

            if needs_restore:
                logger.info(f"Postgres directory is empty, restoring database backup...")
                db_result = restore_database_backup(namespace)
                if db_result["status"] != "success":
                    return {
                        "status": "partial",
                        "message": f"Resource sync succeeded but DB restore failed: {db_result['message']}"
                    }
                logger.info("Database backup restored successfully")
            else:
                logger.info(f"Postgres directory already populated, skipping database restore")

        if all_success:
            return {"status": "success", "message": f"Synced all resources for {application}"}
        else:
            return {"status": "partial", "message": f"Some syncs failed: {failed}"}

    finally:
        # Cleanup all temp key files
        for ssh_key in ssh_keys.values():
            if os.path.exists(ssh_key):
                os.remove(ssh_key)
