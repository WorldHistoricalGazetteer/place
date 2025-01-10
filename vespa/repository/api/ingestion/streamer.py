# /ingestion/streamer.py
import csv
import gzip
import io
import logging
import os
import tempfile
import xml.etree.ElementTree
import zipfile

import ijson
import requests

from ..utils import is_valid_url


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

    def get_stream(self):
        # First, validate the URL before fetching
        if not is_valid_url(self.file_url):
            self.logger.error(f"Invalid URL: {self.file_url}")
            raise ValueError(f"Invalid URL: {self.file_url}")

        self.logger.info(f"Fetching stream for URL: {self.file_url}")
        if self.file_url.endswith('.gz'):
            return self._get_gzip_stream()
        elif self.file_url.endswith('.zip'):
            return self._get_zip_stream()
        else:
            self.logger.error("Unsupported file format")
            raise ValueError("Unsupported file format")

    def _get_gzip_stream(self):
        # Directly stream gzip file from URL
        self.logger.info(f"Fetching gzip stream from {self.file_url}")
        response = requests.get(self.file_url, stream=True)
        response.raise_for_status()
        self.logger.info(f"Successfully fetched gzip file from {self.file_url}")
        return gzip.GzipFile(fileobj=response.raw)

    def _get_zip_stream(self):
        # Download the ZIP file to a temporary file
        self.logger.info(f"Fetching zip stream from {self.file_url}")
        with requests.get(self.file_url, stream=True) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                temp_file_path = temp_file.name

        try:
            # Open the zip file and return the stream of the specified file inside
            self.logger.info(f"Processing ZIP file: {temp_file_path}")
            with zipfile.ZipFile(temp_file_path, 'r') as zip_file:
                if self.file_name not in zip_file.namelist():
                    self.logger.error(f"{self.file_name} not found in the ZIP archive")
                    raise ValueError(f"{self.file_name} not found in the ZIP archive")
                self.logger.info(f"Successfully located {self.file_name} in the ZIP archive")
                return zip_file.open(self.file_name)
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                self.logger.info(f"Temporary file {temp_file_path} has been deleted")

    def get_items(self):
        """
        Parse the stream and yield items based on format (json, csv, or xml).
        """
        stream = self.get_stream()
        format_type = self.file_type

        if format_type in ['json', 'geojson']:
            return self._parse_json_stream(stream)
        elif format_type == 'csv':
            return self._parse_csv_stream(stream)
        elif format_type == 'xml':
            return self._parse_xml_stream(stream)
        elif format_type == 'nt':
            return self._parse_nt_stream(stream)
        else:
            self.logger.error("Unsupported format type")
            raise ValueError("Unsupported format type")

    def _parse_json_stream(self, stream):
        # Using ijson for efficient JSON parsing from stream
        parser = ijson.items(stream, f"{self.item_path}.item")
        for item in parser:
            yield item

    def _parse_csv_stream(self, stream):
        # Parse CSV from stream
        wrapper = io.TextIOWrapper(stream, encoding='utf-8', errors='replace')
        csv_reader = csv.DictReader(wrapper, delimiter=self.delimiter, fieldnames=self.fieldnames)
        for row in csv_reader:
            yield row

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

    def _parse_nt_stream(self, stream):
        wrapper = io.TextIOWrapper(stream, encoding='utf-8', errors='replace')

        for line in wrapper:
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
