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
        self.phonetics = [':pronunciation', ':ipa', ':iso15919']
        self.output = {
            'names': [],
            'toponyms': [],
        }

    def _get_years(self, start_date: str = None, end_date: str = None) -> dict:
        return {
            **({'year_start': year_start} if start_date and (year_start := start_date.split('-')[0]) else {}),
            **({'year_end': year_end} if end_date and (year_end := end_date.split('-')[0]) else {}),
        }

    def _parse_dates(self, dates: str) -> dict:
        complex_dates = dates.split('--')
        if len(complex_dates) == 1:
            simple_dates = dates.split('-')
            return self._get_years(simple_dates[0], simple_dates[1] if len(simple_dates) > 1 else None)
        else:
            return self._get_years(complex_dates[0], complex_dates[1])

    def _process_name(self, type: str, name: str, years: dict):
        """
        Process a name property and add it to the output.

        :param type: The name property key.
        :param name: The name property value.
        :param years: The years dictionary.

        See: https://wiki.openstreetmap.org/wiki/Names
        """

        # logger.info(f'Processing {type} {name} {years}')

        parts = type.split(':')
        name_type = parts[0]  # First part is the name type
        isolanguage = parts[1] if len(parts) > 1 else None
        years = self._parse_dates(parts[2]) if len(parts) > 2 else years

        ipa = next((self.properties[f"{type}{phonetic}"] for phonetic in self.phonetics if f"{type}{phonetic}" in self.properties), None)

        # OSM names should not be multiple values, but are occasionally ";"-separated
        for name in name.split(';'):
            name = name.strip()
            self.output['names'].append({
                'toponym_id': (toponym_id := get_uuid()),
                **years,
                **({'is_preferred': is_preferred} if (is_preferred := name_type == 'name') else {}),
                **({'ipa': ipa} if ipa else {}),
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

        years = self._get_years(self.properties.get('start_date'), self.properties.get('end_date'))

        exclude_startswith = ['source:', 'website:', 'note:', 'name:etymology:', 'start_date:', 'end_date:']
        exclude_contains = [':word_stress', ':prefix', ':suffix']
        replacements = {
            'seamark:landmark:': '',
            ':UN:': ':',
        }

        for key in self.properties:
            for old, new in replacements.items():
                key = key.replace(old, new)
            if (
                    'name' in key
                    and not any(key.startswith(prefix) for prefix in exclude_startswith)
                    and not any(substring in key for substring in exclude_contains + self.phonetics)
            ):
                self._process_name(key, self.properties[key], years)

        return self.output
