import logging
from typing import Dict

from ....utils import get_uuid

logger = logging.getLogger(__name__)


class NamesProcessor:
    def __init__(self, document_id: str, names: Dict[str, Dict[str, str]]):
        """
        :param document_id: The unique ID of the document (place).
        :param names: Dictionary of '<language>' dictionaries containing 'language' and 'value' keys.

        Example:
          "labels": {
            "en": {
              "language": "en",
              "value": "New York City"
            },
            "ar": {
              "language": "ar",
              "value": "\u0645\u062f\u064a\u0646\u0629 \u0646\u064a\u0648 \u064a\u0648\u0631\u0643"
            },
            "fr": {
              "language": "fr",
              "value": "New York City"
            },
            "my": {
              "language": "my",
              "value": "\u1014\u101a\u1030\u1038\u101a\u1031\u102c\u1000\u103a\u1019\u103c\u102d\u102f\u1037"
            },
            "ps": {
              "language": "ps",
              "value": "\u0646\u064a\u0648\u064a\u0627\u0631\u06a9"
            }
          },

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

        for language, name in self.names.items():

            name = name.get(
                'value')  # Unicode escape sequences are automatically converted to their respective UTF-8 characters.

            if not name:
                continue

            self.output['names'].append({
                'toponym_id': (toponym_id := get_uuid()),
                'language': language,
                'year_start': 2025,
                'year_end': 2025,
            })
            self.output['toponyms'].append({
                'document_id': toponym_id,
                'fields': {
                    'name_strict': name,
                    'name': name,
                    'places': [self.document_id],
                    'bcp47_language': language,
                }
            })

        return self.output
