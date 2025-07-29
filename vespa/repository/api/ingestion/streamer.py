# /ingestion/streamer.py
import asyncio
import bz2
import csv
import gzip
import io
import json
import logging
import os
import subprocess
import urllib.parse
import zipfile

import ijson
import requests
import xmltodict

from tqdm import tqdm

logger = logging.getLogger(__name__)


class StreamFetcher:
    """
    A class to fetch and parse data streams from various file types (e.g., JSON, CSV, XML, N-Triple)
    hosted on a URL. It supports fetching compressed files (gzip, zip), parsing data from these
    streams, and optionally applying filters.

    Attributes:
        file_url (str): The URL from which to fetch the file.
        file_type (str): The type of file (e.g., 'json', 'csv', 'xml').
        filter (Optional[dict]): A filter to apply to the parsed data (for N-Triple files).
        file_name (Optional[str]): The name of the specific file inside a ZIP archive.
        item_path (Optional[str]): Path to the items in a JSON file, for JSON parsing.
        fieldnames (Optional[List[str]]): Fieldnames for CSV parsing.
        delimiter (str): Delimiter for CSV files, default is tab ('\t').
        logger (logging.Logger): Logger instance for logging events.

    Methods:
        get_stream():
            Returns a stream of data from the file URL based on the file format (gzip, zip, etc.).

        get_items():
            Parses the data stream based on the file type and returns the items.

        _parse_json_stream(stream):
            Parses a JSON stream and yields items.

        _parse_csv_stream(stream):
            Parses a CSV stream and yields rows.

        _parse_xml_stream(stream):
            Parses an XML stream and yields elements.

        _parse_nt_stream(stream):
            Parses an N-Triple stream and yields subject-predicate-object triples.

        _split_triple(line):
            Splits a line from an N-Triple stream into subject, predicate, and object.

    Exceptions:
        ValueError: Raised if the file format is unsupported or if required elements are not found.
        Exception: Raised for network or file processing errors.
    """

    def __init__(self, file):
        self.logger = logging.getLogger(__name__)
        self.file_url = file['url']  # URL of the file to fetch
        self.file_type = file['file_type']  # Type of the file (json, csv, xml)
        self.filters = file.get('filters', [])  # Filter to apply to triples
        self.file_name = file.get('file_name', None)  # Name of required file inside a ZIP archive
        self.item_path = file.get('item_path', None)  # Path to the items in a JSON file
        self.fieldnames = file.get('fieldnames', None)  # Fieldnames for CSV files
        self.delimiter = file.get('delimiter', '\t')  # Delimiter for CSV files
        self.local_name = file.get('local_name', None)  # Local name for the downloaded file
        self.ingestion_path = "/ix1/whcdh/data"  # Path to the ingestion folder
        self.stream = None

    def close_stream(self):
        """
        Closes the open file or stream, if any.
        """
        if self.stream:
            try:
                if isinstance(self.stream, zipfile.ZipFile):
                    self.stream.close()
                elif hasattr(self.stream, "aclose"):  # async generator
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.stream.aclose())
                else:
                    self.stream.close()  # Close the underlying file object
                self.logger.info(f"Closed stream for {self.file_url}")
            except Exception as e:
                self.logger.error(f"Error closing stream for {self.file_url}: {e}")

    def _is_local_file(self, file_url):
        # Check if the file_url is a valid local file path
        parsed = urllib.parse.urlparse(file_url)
        return not parsed.scheme or parsed.scheme == "file"

    def get_file_path(self):
        """
        Construct the file path where the file will be stored locally.
        Use `local_name` if provided; otherwise, default to the basename of the file URL.
        """
        file_name = self.local_name if self.local_name else os.path.basename(self.file_url)
        return os.path.join(self.ingestion_path, file_name)

    def _download_file(self):
        if self._is_local_file(self.file_url):
            file_path = os.path.abspath(self.file_url)
            if not os.path.exists(file_path):
                self.logger.error(f"Local file does not exist: {file_path}")
                raise FileNotFoundError(f"Local file not found: {file_path}")
            self.logger.info(f"Using existing local file: {file_path}")
            return file_path

        file_path = self.get_file_path()
        if os.path.exists(file_path):
            self.logger.info(f"File already exists at {file_path}, skipping download.")
            return file_path

        self.logger.info(f"Downloading file from {self.file_url} to {file_path}")

        try:
            with requests.get(self.file_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                with open(file_path, 'wb') as f, tqdm(
                        desc=os.path.basename(file_path),
                        total=total,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                ) as bar:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        bar.update(len(chunk))
            self.logger.info(f"File downloaded successfully to {file_path}")
            return file_path

        except requests.RequestException as e:
            self.logger.error(f"Failed to download file: {e}")
            raise

    def get_stream(self):
        try:
            file_path = self._download_file()
            self.logger.info(f"Opening stream for {file_path}")

            # Check for gzip compression by inspecting magic bytes
            with open(file_path, 'rb') as file:
                magic_bytes = file.read(2)
                is_gzip = magic_bytes == b'\x1f\x8b'
                is_bz2 = magic_bytes == b'\x42\x5a'

            if is_gzip:
                self.logger.info(f"Detected gzip compression for file {file_path}")
                return gzip.open(file_path, 'rb')
            elif is_bz2:
                self.logger.info(f"Detected bz2 compression for file {file_path}")
                return bz2.open(file_path, 'rb')
            elif file_path.endswith('.zip'):
                self.logger.info(f"Opening zip archive {file_path}")
                return self._get_zip_stream(file_path)
            else:
                self.logger.info(f"Opening regular file stream for {file_path}")
                return self._get_regular_file_stream(file_path)
        except Exception as e:
            self.logger.error(f"Failed to open stream for {self.file_url}. Error: {e}")
            raise

    def _get_regular_file_stream(self, file_path):
        """Return an asynchronous file stream."""

        async def async_file_stream():
            with open(file_path, 'rb') as file:
                while True:
                    line = await asyncio.to_thread(file.readline)
                    if not line:  # EOF
                        break
                    yield line

        return async_file_stream()

    def _get_zip_stream(self, zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            if self.file_name not in zip_file.namelist():
                self.logger.error(f"{self.file_name} not found in ZIP archive")
                raise ValueError(f"{self.file_name} not found in ZIP archive")
            self.logger.info(f"Extracting {self.file_name} from {zip_path}")
            return zip_file.open(self.file_name)

    def get_items(self):
        """
        Parse the stream and yield items based on format (json, csv, or xml).
        """
        # For this specific Wikidata file, use a specialised parsing method
        if self.file_url == "https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz" and \
                self.file_type == 'json' and self.item_path == 'entities':
            return self._parse_wikidata_entities_stream()
        else:
            self.stream = self.get_stream()  # Call get_stream for other file types
            format_type = self.file_type

            if format_type in ['json', 'geojson']:
                return self._parse_json_stream(self.stream)
            elif format_type == 'ndjson':
                return self._parse_ndjson_stream(self.stream)
            elif format_type == 'geojsonseq':
                return self._parse_geojsonseq_stream(self.stream)
            elif format_type in ['csv', 'tsv', 'txt']:
                return self._parse_csv_stream(self.stream)
            elif format_type == 'xml':
                return self._parse_xml_stream(self.stream)
            elif format_type == 'nt':
                return self._parse_nt_stream(self.stream)
            else:
                self.logger.error(f"Unsupported format type: {format_type}")
                raise ValueError(f"Unsupported format type: {format_type}")

    async def _parse_json_stream(self, stream):
        # ijson is synchronous, run the iteration in a thread to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        iterator = await loop.run_in_executor(
            None,  # Use default ThreadPoolExecutor
            lambda: ijson.items(stream, f"{self.item_path}.*")
        )

        for item in iterator:
            yield item

    # def _parse_json_stream(self, stream):
    #     # Use asyncio.to_thread to run the ijson parsing in a separate thread
    #     parser = asyncio.to_thread(ijson.items, stream, f"{self.item_path}.item")
    #
    #     async def iterator():
    #         # Await the result from asyncio.to_thread and process items in a normal loop
    #         for item in await parser:
    #             yield item
    #
    #     return iterator()

    async def _parse_wikidata_entities_stream(self):
        """
        Specialized method to parse the Wikidata latest-all.json.gz using jq and apply filters.
        """
        file_path = self._download_file()  # Ensure file is downloaded locally

        # Construct the jq command to decompress and extract entities
        # `jq -c '.entities | to_entries[] | .value'` extracts each entity as a compact JSON line.
        cmd = ["gzip", "-dc", file_path, "|", "jq", "-c", ".entities | to_entries[] | .value"]

        self.logger.info(f"Starting jq process: {' '.join(cmd)}")
        process = None
        try:
            # Use shell=True for piping. For untrusted input, prefer separate subprocesses.
            process = await asyncio.create_subprocess_shell(
                ' '.join(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Assign the process to self.stream for proper cleanup in close_stream if needed
            self.stream = process.stdout  # Consider this the stream for closing purposes

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                try:
                    doc = json.loads(line.decode('utf-8'))

                    # Apply all defined filters
                    should_include = True
                    for filter_func in self.filters:
                        if not filter_func(doc):
                            should_include = False
                            break  # No need to check other filters if one fails

                    if should_include:
                        yield doc

                except json.JSONDecodeError as e:
                    self.logger.error(f"Error decoding JSON line from jq output: {line}. Error: {e}")
                    continue

            # Wait for the process to complete and check for errors
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                self.logger.error(f"jq command failed with error: {stderr.decode('utf-8')}")
                raise RuntimeError(f"jq process failed: {stderr.decode('utf-8')}")

        except FileNotFoundError:
            self.logger.error("`jq` command not found. Please ensure `jq` is installed and in your PATH.")
            raise
        except Exception as e:
            self.logger.error(f"Error running jq for Wikidata parsing: {e}")
            raise
        finally:
            if process and process.returncode is None:  # Process is still running
                self.logger.warning("Terminating jq process.")
                process.terminate()
                await process.wait()  # Wait for it to actually terminate
            self.close_stream()  # Ensure cleanup even if process failed/finished

    async def _parse_ndjson_stream(self, stream):
        """
        Asynchronously parses an NDJSON stream and yields each document.
        """

        async for line in stream:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error decoding JSON line: {line}. Error: {e}")
                    raise

    def _parse_geojsonseq_stream(self, stream):
        async def iterator():
            # Process each record one-by-one
            buffer = b""

            async for chunk in stream:
                buffer += chunk

                # Only process when we have enough data to complete a record
                while True:
                    # Find the position of the Record Separator (RS) in the buffer
                    rs_pos = buffer.find(b'\x1e')  # Record Separator is 0x1e (RS)
                    if rs_pos == -1:
                        break  # No more complete records yet, wait for more data

                    # Process the record up to the RS
                    record = buffer[:rs_pos].decode("utf-8").strip()
                    if record:
                        try:
                            yield json.loads(record)  # Yield the parsed JSON object
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Error parsing line: {record}. Error: {e}")
                            raise

                    # Move the buffer past the processed record and RS
                    buffer = buffer[rs_pos + 1:]

        return iterator()

    def _parse_csv_stream(self, stream):
        # Parse CSV from stream
        wrapper = io.TextIOWrapper(stream, encoding='utf-8', errors='replace')
        csv_reader = csv.DictReader(wrapper, delimiter=self.delimiter, fieldnames=self.fieldnames)

        async def async_generator():
            for row in csv_reader:
                await asyncio.sleep(0) # Yield control to the event loop
                yield row

        return async_generator()

    def _parse_xml_stream(self, stream):
        """
        Parse XML from stream.
        """

        async def async_generator():
            # Use xmltodict's streaming mode to process XML elements one by one
            try:
                for doc in xmltodict.parse(stream, item_depth=2):
                    logger.info(f"Yielding XML document: {doc}")
                    yield doc
            except Exception as e:
                self.logger.error(f"Failed to parse XML stream. Error: {e}")
                raise

        # Return the async iterator
        return async_generator()

    def _split_triple(self, line):
        parts = line.rstrip(' .').split(' ', 2)

        if len(parts) != 3:
            self.logger.error(f"Triple must have exactly three components: {line}")
            raise ValueError("Triple must have exactly three components")

        subject, predicate, obj = parts
        return subject, predicate, obj

    async def _parse_nt_stream(self, stream):
        wrapper = io.TextIOWrapper(stream, encoding='utf-8', errors='replace')

        for line in wrapper:
            # Simulate asynchronous I/O
            await asyncio.sleep(0)
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                # Split N-Triple line into three components (subject, predicate, object)
                subject, predicate, obj = self._split_triple(line)

                # TODO: This would work only on a single filter, not a list of filters
                # if self.filters and not predicate in self.filters:
                #     continue

                yield {
                    'subject': subject.strip('<>'),
                    'predicate': predicate.strip('<>'),
                    'object': obj.strip('<>')
                }
            except ValueError as e:
                self.logger.error(f"Failed to parse N-Triple line: {line}. Error: {e}")
                continue
