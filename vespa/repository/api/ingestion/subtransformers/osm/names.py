import logging
from typing import Dict, Any

from ....bcp_47.bcp_47 import parse_bcp47_fields
from ....utils import get_uuid

logger = logging.getLogger(__name__)


class NamesProcessor:
    def __init__(self, document_id: str, properties: Dict[str, Any]):
        """
        :param document_id: The unique ID of the document (place).
        :param properties: The properties of the OSM-derived feature.
        """
        self.document_id = document_id
        self.properties = properties
        self.output = {
            'names': [],
            'toponyms': [],
        }

    def _process_name(self, type: str, name: str, years: dict):
        """
        Process a name property and add it to the output.

        :param type: The name property key.
        :param name: The name property value.
        :param years: The years dictionary.
        """

        # logger.info(f'Processing {type} {name} {years}')

        parts = type.split(':')
        name_type = parts[0]  # First part is the name type
        # TODO: Handle values like "name:fr:1893-1925", and trap others
        if len(parts) > 2:
            logger.warning(f'Unexpected language: {type}')
        # TODO: Validate values in parse_bcp47_fields
        isolanguage = ':'.join(parts[1:]) if len(parts) > 1 else None

        self.output['names'].append({
            'toponym_id': (toponym_id := get_uuid()),
            **years,
            **({'is_preferred': is_preferred} if (is_preferred := name_type == 'name') else {}),
        })
        self.output['toponyms'].append({
            'document_id': toponym_id,
            'fields': {
                'name_strict': name,
                'name': name,
                'places': [self.document_id],
                **(parse_bcp47_fields(isolanguage) if isolanguage else {}),
            }
        })

    def process(self) -> dict:

        years = {
            **({'year_start': year_start} if (year_start := self.properties.get('start_date')) else {}),
            **({'year_end': year_end} if (year_end := self.properties.get('end_date')) else {}),
        }

        for key in self.properties:
            if key.__contains__('name'):
                self._process_name(key, self.properties[key], years)

        return self.output
