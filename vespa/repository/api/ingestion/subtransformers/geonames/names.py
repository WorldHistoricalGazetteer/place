import logging
from typing import List, Dict, Any

from ....utils import get_uuid

logger = logging.getLogger(__name__)


class NamesProcessor:
    def __init__(self, document_id: str, names: List[Dict[str, Any]]):
        """
        :param document_id: The unique ID of the document (place).
        :param names: List of name dictionaries containing identifiers and 'alternate_name', 'isolanguage',
            'isPreferredName', 'from', and 'to'.
        """
        self.document_id = document_id
        self.names = names
        self.output = {
            'names': [],
            'toponyms': [],
        }

    def process(self) -> dict:
        """
        Processes the names and generates `names` and `toponyms` arrays.

        :return: A dictionary with 'names' and 'toponyms' arrays.
        """
        for name in self.names:

            alternateName = name.get("alternate_name")
            if not alternateName:
                continue

            isolanguage = name.get('isolanguage')
            if isolanguage and isolanguage in ["post", "iata", "icao", "faac", "abbr", "link", "wkdt"]:
                # Skip non-language codes, move on to next name
                continue

            years = {
                **({'year_start': year_start} if (year_start := name.get('from')) else {}),
                **({'year_end': year_end} if (year_end := name.get('to')) else {}),
            }

            self.output['names'].append({
                'toponym_id': (toponym_id := name.get("alternateNameId", get_uuid())),
                **years,
                **({'is_preferred': is_preferred} if (is_preferred := name.get('isPreferredName')) else {}),
            })
            self.output['toponyms'].append({
                'document_id': toponym_id,
                'fields': {
                    'name': alternateName,
                    'places': [self.document_id],
                    **({'bcp47_language': isolanguage} if isolanguage else {}),
                }
            })

        return self.output
