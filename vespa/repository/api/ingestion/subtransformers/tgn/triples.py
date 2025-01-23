import logging
import re

logger = logging.getLogger(__name__)


class TriplesProcessor:

    def __init__(self, data: dict):
        """
        :param data: A dictionary containing 'subject', 'predicate', and 'object' keys.
        """
        try:
            self.data = data
            self.subject_id = data.get("subject", "").split('/')[-1].removesuffix("-geometry")
            self.predicate = data.get("predicate", "").split('/')[-1].split('#')[-1]
            self.object = data.get("object", "")
            self.processed = self.process()

            # logger.info(f"TRIPLE: {self.subject_id} *** {self.predicate} *** {self.object}")
        except Exception as e:
            logger.exception(f"Exception during triple processing: {str(e)}", exc_info=True)

    def process(self) -> dict:
        try:
            match self.predicate:
                case "placeType":
                    return {
                        'place': {
                            'document_id': self.subject_id,
                            'fields': {
                                'types': [self.object.split('/')[-1]],
                            }
                        }
                    }
                case "longitude":
                    return {
                        'place': {
                            'document_id': self.subject_id,
                            'fields': {
                                'bbox_sw_lng': float(self.object.split('^^')[0].strip('"')),
                            }
                        }
                    }
                case "latitude":
                    return {
                        'place': {
                            'document_id': self.subject_id,
                            'fields': {
                                'bbox_sw_lat': float(self.object.split('^^')[0].strip('"')),
                            }
                        }
                    }
                case "term":
                    toponym, _, language = self.object.partition("@")
                    return {
                        'toponym': {
                            'document_id': None,  # Generate UUID on first insertion
                            'variant_id': self.subject_id,  # Add toponym UUID to this variant
                            'fields': {
                                'name_strict': (toponym := toponym.strip('"')),
                                'name': toponym,
                                **({'bcp47_language': language} if language else {}),
                            }
                        }
                    }
                case "estStart":
                    match = re.match(r'"(-?\d+)', self.object)
                    if not match:  # Catch rogue values, such as '"######"^^<http://www.w3.org/2001/XMLSchema#gYear'
                        return {}
                    return {
                        'variant': {
                            'document_id': self.subject_id,
                            'fields': {
                                # Sometimes month and day are included, e.g. '"2015-08-28"'
                                'year_start': int(match.group(1)),
                            }
                        }
                    }
                case "estEnd":
                    match = re.match(r'"(-?\d+)', self.object)
                    if not match:  # Catch rogue values, such as '"######"^^<http://www.w3.org/2001/XMLSchema#gYear'
                        return {}
                    return {
                        'variant': {
                            'document_id': self.subject_id,
                            'fields': {
                                # Sometimes month and day are included, e.g. '"2015-08-28"'
                                'year_end': int(match.group(1)),
                            }
                        }
                    }
                case _:  # altLabel, prefLabel, prefLabelGVP
                    variant_id = self.object.split('/')[-1]
                    return {
                        'variant': {
                            'document_id': variant_id,
                            'fields': {
                                'place': self.subject_id,
                                **({'is_preferred': 1} if self.predicate == "prefLabel" else {}),
                                **({'is_preferred_GVP': 1} if self.predicate == "prefLabelGVP" else {}),
                            }
                        }
                    }
        except Exception as e:
            logger.exception(f"Exception during triple processing {self.data}: {str(e)}", exc_info=True)

    def get(self, key, default=None):
        """
        Mimics dictionary .get() behaviour for the processed result.
        """
        return self.processed.get(key, default)
