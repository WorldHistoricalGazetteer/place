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
import xmltodict

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
        self.filter = file.get('filter', None)  # Filter to apply to triples
        self.file_name = file.get('file_name', None)  # Name of required file inside a ZIP archive
        self.item_path = file.get('item_path', None)  # Path to the items in a JSON file
        self.fieldnames = file.get('fieldnames', None)  # Fieldnames for CSV files
        self.delimiter = file.get('delimiter', '\t')  # Delimiter for CSV files
        self.local_name = file.get('local_name', None)  # Local name for the downloaded file
        self.ingestion_path = "/ingestion"  # Path to the ingestion folder
        self.stream = None

    def close_stream(self):
        """
        Closes the open file or stream, if any.
        """
        if self.stream:
            try:
                if isinstance(self.stream, zipfile.ZipFile):
                    self.stream.close()
                elif hasattr(self.stream, "aclose"):  # Check if it's an async generator
                    asyncio.run(self.stream.aclose())
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
        if not os.path.exists(file_path):
            self.logger.info(f"Downloading file from {self.file_url} to {file_path}")
            result = subprocess.run([
                "aria2c", "--dir", os.path.dirname(file_path), "--out", os.path.basename(file_path), self.file_url
            ], check=True)
            if result.returncode == 0:
                self.logger.info(f"File downloaded successfully to {file_path}")
            else:
                self.logger.error(f"Failed to download file from {self.file_url}")
                raise Exception("File download failed")
        else:
            self.logger.info(f"File already exists at {file_path}, skipping download.")
        return file_path

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
        self.stream = self.get_stream()
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

    def _parse_json_stream(self, stream):
        # Use asyncio.to_thread to run the ijson parsing in a separate thread
        parser = asyncio.to_thread(ijson.items, stream, f"{self.item_path}.item")

        async def iterator():
            # Await the result from asyncio.to_thread and process items in a normal loop
            for item in await parser:
                yield item

        return iterator()

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

    # def _parse_ndjson_stream(self, stream):
    #     wrapper = io.TextIOWrapper(stream, encoding="utf-8", errors="replace")
    #
    #     async def iterator():
    #         try:
    #             for line in wrapper:
    #                 # Simulate asynchronous I/O
    #                 await asyncio.sleep(0)
    #                 line = line.strip()
    #                 if line:  # Ignore empty lines
    #                     try:
    #                         yield json.loads(line)  # Parse and yield JSON object
    #                     except json.JSONDecodeError as e:
    #                         self.logger.error(f"Error decoding JSON line: {line}. Error: {e}")
    #                         raise
    #         except Exception as e:
    #             self.logger.error(f"Failed to parse NDJSON stream. Error: {e}")
    #             raise
    #
    #     return iterator()

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
                if self.filter and not predicate in self.filter:
                    continue
                yield {
                    'subject': subject.strip('<>'),
                    'predicate': predicate.strip('<>'),
                    'object': obj.strip('<>')
                }
            except ValueError as e:
                self.logger.error(f"Failed to parse N-Triple line: {line}. Error: {e}")
                continue
