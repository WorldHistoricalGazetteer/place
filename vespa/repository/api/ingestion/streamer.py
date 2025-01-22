# /ingestion/streamer.py
import asyncio
import csv
import gzip
import io
import logging
import os
import urllib.parse
import xml.etree.ElementTree
import zipfile

import ijson
import requests


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

    def _is_local_file(self, file_url):
        # Check if the file_url is a valid local file path
        parsed = urllib.parse.urlparse(file_url)
        return not parsed.scheme or parsed.scheme == "file"

    def _get_file_path(self):
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

        file_path = self._get_file_path()
        if not os.path.exists(file_path):
            self.logger.info(f"Downloading file from {self.file_url} to {file_path}")
            with requests.get(self.file_url, stream=True) as response:
                response.raise_for_status()
                with open(file_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
            self.logger.info(f"File downloaded successfully to {file_path}")
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

            if is_gzip:
                self.logger.info(f"Detected gzip compression for file {file_path}")
                return gzip.open(file_path, 'rb')
            elif file_path.endswith('.zip'):
                self.logger.info(f"Opening zip archive {file_path}")
                return self._get_zip_stream(file_path)
            else:
                self.logger.info(f"Opening regular file stream for {file_path}")
                return open(file_path, 'rb')
        except Exception as e:
            self.logger.error(f"Failed to open stream for {self.file_url}. Error: {e}")
            raise

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
        stream = self.get_stream()
        format_type = self.file_type

        if format_type in ['json', 'geojson']:
            return self._parse_json_stream(stream)
        elif format_type in ['csv', 'tsv', 'txt']:
            return self._parse_csv_stream(stream)
        elif format_type == 'xml':
            return self._parse_xml_stream(stream)
        elif format_type == 'nt':
            return self._parse_nt_stream(stream)
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

    def _parse_csv_stream(self, stream):
        # Parse CSV from stream
        wrapper = io.TextIOWrapper(stream, encoding='utf-8', errors='replace')
        csv_reader = csv.DictReader(wrapper, delimiter=self.delimiter, fieldnames=self.fieldnames)

        async def async_generator():
            for row in csv_reader:
                yield row

        return async_generator()

    def _parse_xml_stream(self, stream):
        # Parse XML incrementally from stream
        for event, elem in xml.etree.ElementTree.iterparse(stream, events=('end',)):
            if elem.tag == 'place':  # Assuming the root element of interest is <item>
                yield elem
                elem.clear()  # Free memory

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
