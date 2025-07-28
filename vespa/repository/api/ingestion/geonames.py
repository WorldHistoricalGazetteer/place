import logging

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher

logger = logging.getLogger(__name__)

config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == 'GeoNames'),
              None)

for _, file_config in enumerate(config['files']):
    logger.info(f"Fetching items from stream: {file_config['url']}")
    stream_fetcher = StreamFetcher(file_config)

    if 'ld_file' in file_config:
        stream_fetcher = StreamFetcher({
            'url': stream_fetcher.get_file_path().replace(file_config['local_name'], file_config['ld_file']),
            'file_type': 'ndjson'
        })

    stream = stream_fetcher.get_items()