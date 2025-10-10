import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PV_MOUNT_ROOT = os.environ.get("PV_MOUNT_ROOT", "/ix1/whcdh")
logger.info(f"PV_MOUNT_ROOT set to: {PV_MOUNT_ROOT}")

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
    "plausible": [
        {
            "remote": "/var/lib/docker/volumes/plausible-ce_db-data/_data/",
            "local": f"{PV_MOUNT_ROOT}/plausible/db-data/",
            "host": "main_host"
        },
        {
            "remote": "/var/lib/docker/volumes/plausible_event-data/_data/",
            "local": f"{PV_MOUNT_ROOT}/plausible/event-data/",
            "host": "main_host"
        }
    ]
    # These are commented out because tiles have already been synced and augmented locally
    # "tileserver": [
    #     {
    #         "remote": "/srv/tileserver/configs",
    #         "local": f"{PV_MOUNT_ROOT}/tileserver/configs",
    #         "host": "tiler_host"
    #     },
    #     {
    #         "remote": "/srv/tileserver/tiles",
    #         "local": f"{PV_MOUNT_ROOT}/tiles",
    #         "host": "tiler_host"
    #     }
    # ]
}

BACKUP_CONFIG = {
    "remote_dir": "/home/whgadmin/backup/whgazetteer-org",
    "local_dir": f"{PV_MOUNT_ROOT}/postgres",
    "host": "main_host"
}


def get_ssh_key_from_secret(key_name: str, namespace: str = "whg", secret_name: str = "whg-secret") -> Optional[str]:
    """
    Extract SSH key from Kubernetes secret and save to temp file.
    Returns path to the key file.
    """
    logger.info(f"Attempting to get SSH key '{key_name}' from secret '{secret_name}' in namespace '{namespace}'")

    try:
        result = subprocess.run(
            ["kubectl", "get", "secret", secret_name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=True
        )

        logger.debug(f"Successfully retrieved secret '{secret_name}'")

        import json
        import base64

        secret_data = json.loads(result.stdout)
        key_b64 = secret_data.get("data", {}).get(key_name)

        if not key_b64:
            logger.error(f"Key '{key_name}' not found in secret '{secret_name}' in namespace '{namespace}'")
            logger.debug(f"Available keys in secret: {list(secret_data.get('data', {}).keys())}")
            return None

        key_content = base64.b64decode(key_b64).decode('utf-8')
        logger.debug(f"Successfully decoded SSH key '{key_name}'")

        # Create temp file for key
        fd, key_path = tempfile.mkstemp(suffix='.pem')
        os.write(fd, key_content.encode('utf-8'))
        os.close(fd)
        os.chmod(key_path, 0o600)

        logger.info(f"SSH key '{key_name}' written to temporary file: {key_path}")
        return key_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get secret '{secret_name}' from namespace '{namespace}': {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Failed to extract SSH key '{key_name}': {e}", exc_info=True)
        return None


def rsync_directory(remote_path: str, local_path: str, ssh_key: str,
                    remote_user: str, remote_host: str) -> bool:
    """
    Rsync a directory from remote host to local path.
    """
    logger.info(f"Starting rsync: {remote_user}@{remote_host}:{remote_path} -> {local_path}")

    try:
        # Ensure local directory exists
        Path(local_path).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured local directory exists: {local_path}")

        remote_source = f"{remote_user}@{remote_host}:{remote_path}/"

        command = [
            "rsync",
            "-avz",
            "--rsync-path", "sudo rsync",
            # "--delete",  # BEWARE: Uncommenting this would delete local files not present on remote, including locally-augmented terrarium.mbtiles
            "-e", f"ssh -i {ssh_key} -o StrictHostKeyChecking=no",
            remote_source,
            local_path
        ]

        logger.debug(f"Rsync command: {' '.join(command[:3])} [ssh options hidden] {remote_source} {local_path}")

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3600
        )

        if result.returncode == 0:
            logger.info(f"Successfully synced {remote_path} to {local_path}")
            logger.debug(f"Rsync output: {result.stdout[:200]}...")  # First 200 chars
            return True
        else:
            logger.error(f"Rsync failed for {remote_path}")
            logger.error(f"Rsync stderr: {result.stderr}")
            logger.debug(f"Rsync stdout: {result.stdout}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Rsync timeout (1 hour) for {remote_path}")
        return False
    except Exception as e:
        logger.error(f"Rsync error for {remote_path}: {e}", exc_info=True)
        return False


def fetch_latest_backup(ssh_key: str, remote_user: str, remote_host: str,
                        remote_backup_dir: str, local_database_dir: str) -> bool:
    """
    Fetch and extract the latest database backup from remote host.
    """
    logger.info(f"Fetching latest backup from {remote_user}@{remote_host}:{remote_backup_dir}")

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

        logger.debug(f"Finding latest backup with command: {find_cmd}")

        result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=True)
        latest_backup = result.stdout.strip()

        if not latest_backup:
            logger.error(f"No backup files found in {remote_backup_dir}")
            return False

        logger.info(f"Found latest backup: {latest_backup}")

        # Fetch backup file
        backup_filename = os.path.basename(latest_backup)
        local_backup_path = os.path.join(local_database_dir, backup_filename)

        logger.info(f"Downloading backup to: {local_backup_path}")

        rsync_cmd = [
            "rsync",
            "-avz",
            "-e", f"ssh -i {ssh_key} -o StrictHostKeyChecking=no",
            f"{remote_user}@{remote_host}:{latest_backup}",
            local_backup_path
        ]

        result = subprocess.run(rsync_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to fetch backup: {result.stderr}")
            return False

        logger.info(f"Backup downloaded successfully")

        # Extract backup
        logger.info(f"Extracting backup to {local_database_dir}...")
        tar_cmd = ["tar", "-xzf", local_backup_path, "-C", local_database_dir]
        result = subprocess.run(tar_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to extract backup: {result.stderr}")
            return False

        logger.info("Backup extracted successfully")

        # Cleanup
        logger.debug(f"Removing temporary backup file: {local_backup_path}")
        os.remove(local_backup_path)

        # Fix permissions
        logger.info("Setting postgres directory permissions (999:999, 700)")
        subprocess.run(["chown", "-R", "999:999", local_database_dir])
        subprocess.run(["chmod", "-R", "700", local_database_dir])

        logger.info("Database backup successfully restored")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed during backup fetch: {e.stderr if e.stderr else str(e)}")
        return False
    except Exception as e:
        logger.error(f"Backup fetch failed: {e}", exc_info=True)
        return False


def restore_database_backup(namespace: str = "whg") -> Dict[str, str]:
    """
    Fetch and restore the latest database backup.
    """
    logger.info(f"Starting database restore for namespace '{namespace}'")

    host_config = REMOTE_CONFIG[BACKUP_CONFIG["host"]]
    logger.debug(f"Using host config: {BACKUP_CONFIG['host']} ({host_config['host']})")

    ssh_key = get_ssh_key_from_secret(host_config["secret_key"], namespace)
    if not ssh_key:
        logger.error("Failed to get SSH key for database restore")
        return {"status": "error", "message": "Failed to get SSH key"}

    try:
        success = fetch_latest_backup(
            ssh_key,
            host_config["user"],
            host_config["host"],
            BACKUP_CONFIG["remote_dir"],
            BACKUP_CONFIG["local_dir"]
        )

        if success:
            logger.info("Database restore completed successfully")
            return {"status": "success", "message": "Database restored"}
        else:
            logger.error("Database restore failed")
            return {"status": "error", "message": "Failed to restore database"}

    finally:
        if os.path.exists(ssh_key):
            logger.debug(f"Cleaning up temporary SSH key: {ssh_key}")
            os.remove(ssh_key)


def sync_resource(application: str, namespace: str = "whg") -> Dict[str, str]:
    """
    Sync all resources for a specific application.
    """
    logger.info(f"Starting resource sync for application '{application}' in namespace '{namespace}'")

    if application not in SYNC_PATHS:
        logger.info(f"No remote sync configuration found for '{application}' - skipping")
        return {"status": "skipped", "message": f"No sync configuration for {application}"}

    configs = SYNC_PATHS[application]
    logger.info(f"Found {len(configs)} sync paths for '{application}'")

    results = []
    ssh_keys = {}

    try:
        for i, config in enumerate(configs, 1):
            logger.info(f"Processing sync path {i}/{len(configs)}: {config['remote']}")

            host_config = REMOTE_CONFIG[config["host"]]
            secret_key_name = host_config["secret_key"]

            logger.debug(f"Using host '{config['host']}' ({host_config['host']}) with key '{secret_key_name}'")

            # Get SSH key (cached if already retrieved)
            if secret_key_name not in ssh_keys:
                logger.debug(f"SSH key '{secret_key_name}' not cached, retrieving...")
                ssh_key = get_ssh_key_from_secret(secret_key_name, namespace)
                if not ssh_key:
                    logger.error(f"Failed to get SSH key '{secret_key_name}' - aborting sync")
                    return {"status": "error", "message": f"Failed to get SSH key: {secret_key_name}"}
                ssh_keys[secret_key_name] = ssh_key
                logger.debug(f"SSH key '{secret_key_name}' retrieved and cached")
            else:
                ssh_key = ssh_keys[secret_key_name]
                logger.debug(f"Using cached SSH key '{secret_key_name}'")

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

            logger.info(f"Sync path {i}/{len(configs)} {'succeeded' if success else 'failed'}")

        # Check if all syncs succeeded
        all_success = all(r["success"] for r in results)
        failed = [r["path"] for r in results if not r["success"]]

        if failed:
            logger.warning(f"Failed sync paths: {failed}")

        # Database restore logic for whg
        if application == "whg" and all_success:
            postgres_dir = BACKUP_CONFIG["local_dir"]
            logger.info(f"Checking if database restore is needed for whg (postgres_dir: {postgres_dir})")

            needs_restore = (
                    not os.path.exists(postgres_dir) or
                    len(os.listdir(postgres_dir)) == 0
            )

            if needs_restore:
                logger.info(f"Postgres directory is empty or missing - triggering database restore")
                db_result = restore_database_backup(namespace)
                if db_result["status"] != "success":
                    logger.error(f"Database restore failed: {db_result['message']}")
                    return {
                        "status": "partial",
                        "message": f"Resource sync succeeded but DB restore failed: {db_result['message']}"
                    }
                logger.info("Database backup restored successfully")
            else:
                logger.info(f"Postgres directory already populated - skipping database restore")

        if all_success:
            logger.info(f"All resources synced successfully for '{application}'")
            return {"status": "success", "message": f"Synced all resources for {application}"}
        else:
            logger.warning(f"Partial sync for '{application}': {len(failed)} path(s) failed")
            return {"status": "partial", "message": f"Some syncs failed: {failed}"}

    except Exception as e:
        logger.error(f"Unexpected error during sync for '{application}': {e}", exc_info=True)
        return {"status": "error", "message": f"Sync failed with exception: {str(e)}"}

    finally:
        # Cleanup all temp key files
        logger.debug(f"Cleaning up {len(ssh_keys)} temporary SSH key file(s)")
        for key_name, ssh_key in ssh_keys.items():
            if os.path.exists(ssh_key):
                os.remove(ssh_key)
                logger.debug(f"Removed temporary key file for '{key_name}'")