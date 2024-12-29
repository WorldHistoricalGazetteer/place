import json
import os
import sys

import mbutil


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

    mbutil.disk_to_mbtiles(input_dir, output_file)
