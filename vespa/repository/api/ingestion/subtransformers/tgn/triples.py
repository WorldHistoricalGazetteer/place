import logging

logger = logging.getLogger(__name__)


class TriplesProcessor:

    def __init__(self, data: dict):
        """
        :param data: A dictionary containing 'subject', 'predicate', and 'object' keys.
        """
        self.subject_id = data.get("subject", "").split('/')[-1].removesuffix("-geometry")
        self.predicate = data.get("predicate", "").split('/')[-1].split('#')[-1]
        self.object = data.get("object", "")
        self.processed = self.process()

        logger.info(f"{self.subject_id} *** {self.predicate} *** {self.object}")

    def process(self) -> dict:
        match self.predicate:
            case "longitude":
                return {
                    'schema': 'place',
                    'document_id': self.subject_id,
                    'fields': {
                        'bbox_sw_lng': float(self.object.split('^^')[0].strip('"')),
                    }
                }
            case "latitude":
                return {
                    'schema': 'place',
                    'document_id': self.subject_id,
                    'fields': {
                        'bbox_sw_lat': float(self.object.split('^^')[0].strip('"')),
                    }
                }
            case "term":
                toponym, _, language = self.object.partition("@")
                return {
                    'schema': 'toponym',
                    'document_id': self.subject_id,
                    'fields': {
                        'name_strict': (toponym := toponym.strip('"')),
                        'name': toponym,
                        **({'bcp47_language': language} if language else {}),
                    }
                }
            case "estStart":
                return {
                    'schema': 'variant',
                    'document_id': self.subject_id,
                    'fields': {
                        'year_start': int(self.object.split('^^')[0]),
                    }
                }
            case "estEnd":
                return {
                    'schema': 'variant',
                    'document_id': self.subject_id,
                    'fields': {
                        'year_end': int(self.object.split('^^')[0]),
                    }
                }
            case "altLabel":
                return {
                    'schema': 'variant',
                    'document_id': self.object.split('/')[-1],
                    'fields': {
                        'place': self.subject_id,
                    }
                }
            case _:  # prefLabel, prefLabelGVP
                return {
                    'schema': 'variant',
                    'document_id': self.object.split('/')[-1],
                    'fields': {
                        'place': self.subject_id,
                        'is_preferred': True,
                    }
                }

    def get(self, key, default=None):
        """
        Mimics dictionary .get() behaviour for the processed result.
        """
        return self.processed.get(key, default)
