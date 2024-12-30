from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

LOCAL_DATA_DIR = "/data/k8s/tileserver/data"
LOCAL_TILES_DIR = "/data/k8s/tiles"

logger = logging.getLogger(__name__)


def flip_y(zoom, y):
    return (2 ** zoom - 1) - y


def mbtiles_setup(cur):
    cur.execute("""
        create table tiles (
            zoom_level integer,
            tile_column integer,
            tile_row integer,
            tile_data blob);
            """)
    cur.execute("""create table metadata
        (name text, value text);""")
    cur.execute("""create unique index name on metadata (name);""")
    cur.execute("""create unique index tile_index on tiles
        (zoom_level, tile_column, tile_row);""")


def mbtiles_connect(mbtiles_file):
    try:
        con = sqlite3.connect(mbtiles_file)
        return con
    except Exception as e:
        logger.error("Could not connect to database")
        logger.exception(e)
        sys.exit(1)


def optimize_connection(cur):
    cur.execute("""PRAGMA synchronous=0""")
    cur.execute("""PRAGMA locking_mode=EXCLUSIVE""")
    cur.execute("""PRAGMA journal_mode=DELETE""")


def optimize_database(cur):
    logger.debug('analyzing db')
    cur.execute("""ANALYZE;""")
    logger.debug('cleaning db')
    cur.commit()
    cur.execute("""VACUUM;""")


def disk_to_mbtiles(directory_path, mbtiles_file, **kwargs):
    logger.info("Importing disk to MBTiles")
    sys.stdout.write(f"Importing disk to MBTiles: {directory_path} --> {mbtiles_file}\n")
    if kwargs.get('scheme') == 'xyz':
        sys.stdout.write("Using XYZ scheme\n")
    else:
        sys.stdout.write("Using TMS scheme\n")
    logger.debug("%s --> %s" % (directory_path, mbtiles_file))
    con = mbtiles_connect(mbtiles_file)
    cur = con.cursor()
    try:
        optimize_connection(cur)
        mbtiles_setup(cur)
        image_format = 'png'
        grid_warning = True

        # Process metadata.json
        try:
            metadata = json.load(open(os.path.join(directory_path, 'metadata.json'), 'r'))
            image_format = metadata.get('format', 'png')
            for name, value in metadata.items():
                cur.execute('insert into metadata (name, value) values (?, ?)',
                            (name, value))
            logger.info('metadata from metadata.json restored')
        except IOError:
            logger.warning('metadata.json not found')

        count = 0
        start_time = time.time()
        msg = ""
        for r1, zs, ignore in os.walk(directory_path):
            for z in zs:
                for r2, xs, ignore in os.walk(os.path.join(r1, z)):
                    for x in xs:
                        for r2, ignore, ys in os.walk(os.path.join(r1, z, x)):
                            for y in ys:
                                y, ext = y.split('.', 1)
                                if (ext == image_format):
                                    with open(os.path.join(r1, z, x, y + '.' + ext), 'rb') as f:
                                        original_y = y
                                        if kwargs.get('scheme') == 'xyz':
                                            y = flip_y(int(z), int(y))
                                        cur.execute("""insert into tiles (zoom_level,
                                            tile_column, tile_row, tile_data) values
                                            (?, ?, ?, ?);""",
                                                (z, x, y, sqlite3.Binary(f.read())))
                                    count += 1
                                    if count % 100 == 0:
                                        sys.stdout.write(f"\r{count} tiles inserted ({round(count / (time.time() - start_time))} tiles/sec)")
                                elif (ext == 'grid.json'):
                                    if grid_warning:
                                        logger.warning('grid.json interactivity import not yet supported\n')
                                        grid_warning = False
        logger.debug('tiles inserted.')
        optimize_database(con)

    finally:
        con.commit()
        con.close()
        logger.info("Importing disk to MBTiles complete, database connection closed.")


def print_flush(message):
    print(message)
    sys.stdout.flush()


def create_metadata_file(output_dir, metadata):
    metadata_file = os.path.join(output_dir, "metadata.json")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=4)
    print(f"Metadata saved to {metadata_file}")


def dir_to_mbtiles(input_dir, output_file, metadata):
    if os.path.exists(output_file):
        os.remove(output_file)
        print(f"Deleted existing MBTiles file: {output_file}")

    # Create the metadata.json file
    create_metadata_file(input_dir, metadata)

    disk_to_mbtiles(input_dir, output_file, scheme='xyz')


def download_file(s3_client, bucket_name, file_name, local_path, prefix):
    try:
        s3_client.download_file(bucket_name, f"{prefix}{file_name}", local_path)
        print_flush(f"Downloaded {file_name}")
    except Exception as e:
        print_flush(f"Error downloading {file_name}: {e}")


def download_files(local_path, zoom_range, bucket_name="elevation-tiles-prod", prefix="terrarium/"):
    # Set up S3 client with no-sign-request option
    print_flush("Setting up S3 client...")
    s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))

    local_path = Path(local_path)

    for zoom in zoom_range:
        # First, create the subfolders for each zoom level
        for x in range(2 ** zoom):
            (local_path / str(zoom) / str(x)).mkdir(parents=True, exist_ok=True)

        # Set up ThreadPoolExecutor for concurrent downloads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            file_names = [f"{zoom}/{x}/{y}.png" for x in range(2 ** zoom) for y in range(2 ** zoom)]
            for file_name in file_names:
                file_path = Path.joinpath(local_path, file_name)
                if not file_path.exists():
                    futures.append(executor.submit(download_file, s3_client, bucket_name, file_name, file_path, prefix))

            # Wait for all downloads to complete
            for future in as_completed(futures):
                try:
                    future.result()  # Raise any exception from the thread
                except Exception as e:
                    print_flush(f"Error during file download: {e}")


def terrarium_download(range_start=0, range_end=21):
    zoom_range = range(range_start, range_end + 1)  # Inclusive range

    # Check that local directories are writable
    if not os.access(LOCAL_DATA_DIR, os.W_OK):
        raise PermissionError(f"Directory {LOCAL_DATA_DIR} is not writable.")
    if not os.access(LOCAL_TILES_DIR, os.W_OK):
        raise PermissionError(f"Directory {LOCAL_TILES_DIR} is not writable.")

    data_dir = Path(LOCAL_DATA_DIR) / "terrarium"

    download_files(data_dir, zoom_range)

    # Identify actually-downloaded zoom levels by checking subfolder structure
    zoom_levels = [
        int(subfolder.name) for subfolder in data_dir.iterdir()
        if subfolder.is_dir() and any(item.is_dir() for item in subfolder.iterdir())
    ]

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
        "format": "png",
        "bounds": "-180.0,-85.05112877980659,180.0,85.05112877980659",  # World extent in WGS84
        "center": "0.0,0.0,2",  # Longitude, latitude, zoom level
        "minzoom": str(minzoom),
        "maxzoom": str(maxzoom),
    }

    dir_to_mbtiles(data_dir, os.path.join(LOCAL_TILES_DIR, "terrarium.mbtiles"), metadata)


terrarium_download(0, 10)
