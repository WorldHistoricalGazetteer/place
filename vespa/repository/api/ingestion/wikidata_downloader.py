import os
import requests
import gzip
import ijson
import json
from decimal import Decimal

def serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def filter_wikidata_stream_with_counter(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)  # Ensure the directory exists
    output_file = os.path.join(output_dir, 'wikidata_locations.jsonl')

    response = requests.get(url, stream=True)
    response.raise_for_status()  # Ensure the request is successful

    processed_count = 0
    filtered_count = 0

    with gzip.GzipFile(fileobj=response.raw) as gz_file, open(output_file, 'w') as outfile:
        for entity in ijson.items(gz_file, 'item'):
            processed_count += 1
            if 'claims' in entity and 'P625' in entity['claims']:
                filtered_entity = {
                    'id': entity.get('id'),
                    'labels': entity.get('labels', {}),
                    'claims': {
                        'P625': entity['claims']['P625']
                    }
                }
                # Add paths for AAT type or GeoNames FeatureClass determination
                for prop in ['P31', 'P1566']:
                    if prop in entity['claims']:
                        filtered_entity['claims'][prop] = entity['claims'][prop]

                # Write filtered entity to output
                outfile.write(json.dumps(filtered_entity, default=serialize) + '\n')
                filtered_count += 1

            # Print progress every 10,000 items
            if processed_count % 10000 == 0:
                print(f"Processed: {processed_count}, Filtered: {filtered_count}")

    print(f"Processing completed. Total processed: {processed_count}, Total filtered: {filtered_count}")

# Usage
filter_wikidata_stream_with_counter(
    'https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz',
    '/data/k8s/vespa-ingestion/'
)
