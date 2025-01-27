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
        """

2025-01-27 08:55:24,244 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:ru:word_stress
2025-01-27 08:55:24,245 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: old_name:fr:1893-1925
2025-01-27 08:55:24,245 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,246 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: old_name:ang:597-886
2025-01-27 08:55:24,246 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: old_name:ang:886-1066
2025-01-27 08:55:24,246 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: old_name:en:886-1066
2025-01-27 08:55:24,246 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: old_name:la:47-500
2025-01-27 08:55:24,247 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:etymology:wikidata
2025-01-27 08:55:24,248 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,312 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,327 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,350 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:24,350 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,943 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:24,944 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:alt_name:xdk
2025-01-27 08:55:24,944 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:24,944 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:xdk
2025-01-27 08:55:26,158 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:etymology:wikidata
2025-01-27 08:55:26,158 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:etymology:wikipedia
2025-01-27 08:55:26,540 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:etymology:wikidata
2025-01-27 08:55:26,540 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:27,270 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:27,270 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:old_name:oc
2025-01-27 08:55:29,205 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: seamark:landmark:name
2025-01-27 08:55:30,142 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,177 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,190 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,191 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:en:pronunciation
2025-01-27 08:55:30,191 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:fr:pronunciation
2025-01-27 08:55:30,191 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,822 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:en:ipa
2025-01-27 08:55:30,823 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,823 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,823 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,823 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,875 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,884 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,890 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,902 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:30,909 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:30,985 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:31,179 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:31,179 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:31,180 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:31,180 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:32,150 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:33,022 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:33,285 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:33,286 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:34,066 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:34,066 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:34,485 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:35,662 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:35,662 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:35,681 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:35,733 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:35,746 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: name:en:pronunciation
2025-01-27 08:55:35,747 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:35,747 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:35,768 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:oc
2025-01-27 08:55:40,917 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br
2025-01-27 08:55:42,588 - api.ingestion.subtransformers.osm.names - WARNING - Unexpected language: source:name:br   
        
        """
        if len(parts) > 2:
            logger.warning(f'Unexpected language: {type} {name}')
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
            key = key.replace('seamark:landmark:', '').replace(':UN:', ':')
            if key.__contains__('name') and not key.startswith('source:') and not key.startswith(
                    'website:') and not key.startswith(
                    'note:') and not key.startswith('name:etymology:') and not key.__contains__(':word_stress'):
                self._process_name(key, self.properties[key], years)

        return self.output
