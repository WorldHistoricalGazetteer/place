import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from tileserver.repository.api.utils.utils import dir_to_mbtiles, print_flush

LOCAL_DATA_DIR = "/data/k8s/tileserver/data"
LOCAL_TILES_DIR = "/data/k8s/tiles"


def list_objects_v2_paged(s3_client, bucket_name, prefix, continuation_token=None):
    """Helper function to list objects in the S3 bucket, handling pagination."""
    params = {
        "Bucket": bucket_name,
        "Prefix": prefix
    }
    if continuation_token:
        params["ContinuationToken"] = continuation_token

    response = s3_client.list_objects_v2(**params)
    return response


def get_file_folders(s3_client, bucket_name="elevation-tiles-prod", prefix="terrarium/"):
    file_names = []
    folders = set()

    # Using ThreadPoolExecutor to parallelize the paginated requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        next_token = None

        # Start the first list_objects_v2 call
        futures.append(executor.submit(list_objects_v2_paged, s3_client, bucket_name, prefix, next_token))

        while futures:
            # Wait for the first future to complete
            future = futures.pop(0)
            response = future.result()  # Get the result (response)

            contents = response.get("Contents", [])
            for result in contents:
                key = result.get("Key")
                if key.endswith(".png"):
                    file_names.append(key)
                    folder, _ = os.path.split(key)
                    folders.add(folder)
            print_flush(f"Identified {len(file_names)} tiles in {len(folders)} folders.")

            # Handle pagination: If there's a continuation token, queue the next request
            next_token = response.get("NextContinuationToken")
            if next_token:
                futures.append(executor.submit(list_objects_v2_paged, s3_client, bucket_name, prefix, next_token))

    return file_names, folders


def filter_files(local_dir, file_names):
    """Filter out files that already exist locally."""
    print_flush(f"Filtering {len(file_names)} files...")
    fetch_files = set()
    for file_name in file_names:
        local_file_path = Path(local_dir) / file_name
        if not local_file_path.exists():  # Only keep files that do not exist locally
            fetch_files.add(file_name)
    print_flush(f"...reduced to {len(fetch_files)} files.")
    return fetch_files


def download_file(s3_client, bucket_name, file_name, local_path):
    try:
        s3_client.download_file(bucket_name, file_name, str(local_path))
        print_flush(f"Downloaded {file_name}")
    except Exception as e:
        print_flush(f"Error downloading {file_name}: {e}")


def download_files(s3_client, bucket_name, local_path, file_names, folders):
    local_path = Path(local_path)

    for folder in folders:
        folder_path = Path.joinpath(local_path, folder)
        folder_path.mkdir(parents=True, exist_ok=True)

    # Set up ThreadPoolExecutor for concurrent downloads
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []

        # Download files concurrently
        for file_name in file_names:
            file_path = Path.joinpath(local_path, file_name)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            futures.append(executor.submit(download_file, s3_client, bucket_name, file_name, file_path))

        # Wait for all downloads to complete
        for future in as_completed(futures):
            future.result()  # Handle exceptions raised during download


def terrarium_download(range_start=0, range_end=23):

    # Check that local directories are writable
    if not os.access(LOCAL_DATA_DIR, os.W_OK):
        raise PermissionError(f"Directory {LOCAL_DATA_DIR} is not writable.")
    if not os.access(LOCAL_TILES_DIR, os.W_OK):
        raise PermissionError(f"Directory {LOCAL_TILES_DIR} is not writable.")

    # Set up S3 client with no-sign-request option
    print_flush("Setting up S3 client...")
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    bucket_name = "elevation-tiles-prod"
    data_dir = os.path.join(LOCAL_DATA_DIR, "terrarium")
    inventory = os.path.join(data_dir, "file_folders.json")

    # Get the list of file names and folders, if it exists
    if os.path.exists(inventory):
        with open(inventory, "r") as f:
            data = json.load(f)
            file_names = set(data["file_names"])
            folders = set(data["folders"])
    else:
        file_names, folders = get_file_folders(s3)
        # Save the list of files and folders to a JSON file
        with open(inventory, "w") as f:
            json.dump({"file_names": list(file_names), "folders": list(folders)}, f)

    download_filenames = filter_files(data_dir, file_names)
    download_files(
        s3,
        bucket_name,
        data_dir,
        download_filenames,
        folders
    )

    # Convert folder names to integers
    zoom_levels = [int(folder.split("/")[1]) for folder in folders]

    minzoom = min(zoom_levels)
    maxzoom = max(zoom_levels)

    # Add MBTiles metadata according to the specification
    metadata = {
        "name": "Terrarium DEM",
        "type": "baselayer",
        "version": "1.0.0",
        "description": (
            "This dataset contains elevation data derived from NASA, NGA, and USGS sources, "
            "curated and made available by the Mapzen project. The Terrarium elevation model "
            "provides a global view of terrain at varying levels of detail, ranging from "
            f"zoom levels {minzoom} to {maxzoom}. The data are intended for use in geographic, "
            "environmental, and visualisation applications."
        ),
        "attribution": (
            "DEM: ©<a href='https://mapzen.com'>Mapzen</a> "
            "<a href='https://github.com/mapzen/terrarium'>Terrarium</a>"
        ),
        "format": "pbf",
        "bounds": "-180.0,-85.05112877980659,180.0,85.05112877980659",  # World extent in WGS84
        "center": "0.0,0.0,2",  # Longitude, latitude, zoom level
        "minzoom": str(minzoom),
        "maxzoom": str(maxzoom),
    }

    dir_to_mbtiles(data_dir, os.path.join(LOCAL_TILES_DIR, "terrarium.mbtiles"), metadata)


terrarium_download()
