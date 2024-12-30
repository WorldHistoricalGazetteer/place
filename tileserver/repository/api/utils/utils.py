import json
import os
import sys
import uuid

import mbutil


def generate_random_suffix() -> str:
    """Generates a random suffix string using UUID."""
    return str(uuid.uuid4().hex[:12])  # First 12 characters for brevity


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
