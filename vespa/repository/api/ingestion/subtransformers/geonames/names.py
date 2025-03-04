import logging
from typing import Dict, Any

from ....bcp_47.bcp_47 import parse_bcp47_fields
from ....utils import get_uuid

logger = logging.getLogger(__name__)


class NamesProcessor:
    def __init__(self, document_id: str, name: Dict[str, Any]):
        """
        :param document_id: The unique ID of the document (place).
        :param names: List of name dictionaries containing identifiers and 'alternate_name', 'isolanguage',
            'isPreferredName', 'from', and 'to'.
        """
        self.document_id = document_id
        self.name = name
        self.output = {
            'names': [],
            'toponyms': [],
            'links': [],
        }

    def process(self) -> dict:
        """
        Processes the names and generates `names` and `toponyms` arrays.

        :return: A dictionary with 'names' and 'toponyms' arrays.
        """

        # logger.info(f"Processing names for document {self.document_id}: {len(self.name)} names found. {self.name}")

        alternateName = self.name.get("alternate_name")
        if not alternateName:
            return self.output

        isolanguage = self.name.get('isolanguage')
        match isolanguage:
            case "phon":
                isolanguage = "en-fonipa"
            case "piny":
                isolanguage = "zh-Latn-pinyin"
            case "fr_1793":
                isolanguage = "fr"
                self.name["from"] = self.name.get('from', '1793')  # Such names persisted for different periods

        if isolanguage == 'wkdt':
            self.output['links'].append({
                'record_id': self.document_id,
                'place_curie': f'gn:{self.document_id}',
                'predicate': 'owl:sameAs',
                'object': f'wd:{alternateName}',
            })
            return self.output

        years = {
            # **({'year_start': int(year_start)} if (year_start := self.name.get('from')) else {}),
            # **({'year_end': int(year_end)} if (year_end := self.name.get('to')) else {}),
            'year_start': int(self.name.get('from') or 2025),
            'year_end': int(self.name.get('to') or 2025),
        }

        self.output['names'].append({
            'toponym_id': (toponym_id := self.name.get("alternateNameId", get_uuid())),
            **years,
            **({'is_preferred': is_preferred} if (is_preferred := self.name.get('isPreferredName')) else {}),
        })
        self.output['toponyms'].append({
            'id': toponym_id,
            'fields': {
                'name_strict': alternateName,
                'name': alternateName,
                'places': [self.document_id],
                **(parse_bcp47_fields(isolanguage) if isolanguage else {}),
            }
        })

        return self.output
