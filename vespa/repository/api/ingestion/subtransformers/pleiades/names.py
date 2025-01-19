import logging
import re
from typing import List, Dict, Any

from ....utils import get_uuid, debracket

logger = logging.getLogger(__name__)


class NamesProcessor:
    def __init__(self, document_id: str, names: List[Dict[str, Any]], title: str):
        """
        :param document_id: The unique ID of the document (place).
        :param names: List of name dictionaries containing (inter alia) 'attested', 'romanized', 'language', 'start', and 'end'.
        """
        self.document_id = document_id
        self.names = names if len(names) > 0 else [{"attested": title}]
        self.output = {
            'names': [],
            'toponyms': [],
        }

    def _expand_bracket(self, toponym: str) -> List[str]:
        """
        Processes square-bracketed toponyms:
        1. Removes enclosing brackets if the entire toponym is bracketed.
        2. Generates variations for optional characters within brackets.

        "[Dudjayl]" -> ["Dudjayl"]
        "Μο[υ]τίνη" -> ["Μοτίνη", "Μουτίνη"]
        """
        # Remove enclosing square brackets if the entire toponym is enclosed
        toponym = re.sub(r'^\[(.*?)\]$', r'\1', toponym)

        # Return if no brackets remain
        if '[' not in toponym:
            return [toponym]

        results = []
        # Add result with all brackets removed
        results.append(re.sub(r'\[|\]', '', toponym))
        # Add result with optional characters removed
        results.append(re.sub(r'\[.*?\]', '', toponym))

        return results

    def _process_name(self, toponym: str, toponym_language: str, years: Dict[str, int]) -> None:
        """
        Processes a single toponym and updates the output dictionary.

        :param toponym: The name of the toponym (attested or romanized).
        :param toponym_language: The language of the toponym in BCP 47 format.
        :param years: A dictionary containing 'year_start' and/or 'year_end'.
        """
        # TODO: Query handling of Pleiades `names.attested` or `names.romanized` which may be a single CSV string like this:
        # 'Madīnat aš-Šaʿb, Madinat ash-Sha'b, Medinat esh-Sha'b, Madinat ash-Shab, Medinat esh-Shab, Madinat ash-Shaab, Medinat esh-Shaab, Madinat al-Sha'b, Medinat el-Sha'b, Madinat al-Shab, Medinat el-Shab, Madinat al-Shaab, Medinat el-Shaab, Madinat al-Sha'ab, Medinat el-Sha'ab, Madinat ash-Sha'ab, Medinat esh-Sha'ab, Medīnat eš-Šaʿb'

        toponyms = debracket(toponym).split(", ")
        expanded_toponyms = []
        for split_toponym in toponyms:
            expanded_toponyms.extend(self._expand_bracket(split_toponym))

        for expanded_toponym in expanded_toponyms:
            toponym_id = get_uuid()
            self.output['names'].append({
                'toponym_id': toponym_id,
                **years,
            })
            self.output['toponyms'].append({
                'document_id': toponym_id,
                'fields': {
                    'name': expanded_toponym,
                    'places': [self.document_id],
                    'bcp47_language': toponym_language,
                }
            })

    def process(self) -> dict:
        """
        Processes the names and generates `names` and `toponyms` arrays.

        :return: A dictionary with 'names' and 'toponyms' arrays.
        """
        for name in self.names:
            # Pleiades sometimes has both 'attested' and 'romanized' names: use both if `language` is not "la"
            attested = name.get('attested')
            romanized = name.get('romanized')
            language = name.get('language', 'und')  # Default to 'und' if language is missing

            if not attested and not romanized:
                continue

            years = {
                **({'year_start': name['start']} if 'start' in name else {}),
                **({'year_end': name['end']} if 'end' in name else {}),
            }

            is_latin = language == 'la' or attested == romanized

            if attested:
                self._process_name(attested, language, years)

            if not is_latin and romanized:
                self._process_name(romanized, 'la', years)

        return self.output
