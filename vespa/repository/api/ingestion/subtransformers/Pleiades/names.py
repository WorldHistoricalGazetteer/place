from typing import List, Dict, Any

from ....utils import get_uuid


class NamesProcessor:
    def __init__(self, document_id: str, names: List[Dict[str, Any]]):
        """
        :param document_id: The unique ID of the document (place).
        :param names: List of name dictionaries containing (inter alia) 'attested', 'romanized', 'language', 'start', and 'end'.
        """
        self.document_id = document_id
        self.names = names

    def process(self) -> dict:
        """
        Processes the names and generates `names` and `toponyms` arrays.

        :return: A dictionary with 'names' and 'toponyms' arrays.
        """
        names = []
        toponyms = []
        for name in self.names:
            # Pleiades sometimes has both 'attested' and 'romanized' names: use both if `language` is not "la"
            attested = name.get('attested')
            romanized = name.get('romanized')
            language = name.get('language')

            if not attested and not romanized:
                continue

            years = {
                **({'year_start': name['start']} if 'start' in name else {}),
                **({'year_end': name['end']} if 'end' in name else {}),
            }

            is_latin = language == 'la' or attested == romanized

            def process_name():
                toponym_id = get_uuid()
                names.append({
                    'toponym_id': toponym_id,
                    **years,
                })
                toponyms.append({
                    'document_id': toponym_id,
                    'fields': {
                        'name': attested,
                        'places': [self.document_id],
                        **({'bcp47_language': language} if language else {}),
                    }
                })

            if attested:
                toponym_id = get_uuid()
                names.append({
                    'toponym_id': toponym_id,
                    **years,
                })
                toponyms.append({
                    'document_id': toponym_id,
                    'fields': {
                        'name': attested,
                        'places': [self.document_id],
                        **({'bcp47_language': language} if language else {}),
                    }
                })

            if not is_latin and romanized:
                toponym_id = get_uuid()
                names.append({
                    'toponym_id': toponym_id,
                    **years,
                })
                toponyms.append({
                    'document_id': toponym_id,
                    'fields': {
                        'name': romanized,
                        'places': [self.document_id],
                        'bcp47_language': 'la',
                    }
                })

        return {'names': names, 'toponyms': toponyms}
