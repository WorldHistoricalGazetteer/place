import logging

logger = logging.getLogger(__name__)


class TriplesProcessor:

    def __init__(self, data: dict):
        """
        :param data: A dictionary containing 'subject', 'predicate', and 'object' keys.
        """
        try:
            self.subject_id = data.get("subject", "").split('/')[-1].removesuffix("-geometry")
            self.predicate = data.get("predicate", "").split('/')[-1].split('#')[-1]
            self.object = data.get("object", "")
            self.processed = self.process()

            logger.info(f"TRIPLE: {self.subject_id} *** {self.predicate} *** {self.object}")
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
                            'document_id': self.subject_id,
                            'fields': {
                                'name_strict': (toponym := toponym.strip('"')),
                                'name': toponym,
                                **({'bcp47_language': language} if language else {}),
                            }
                        }
                    }
                case "estStart":
                    return {
                        'variant': {
                            'document_id': self.subject_id,
                            'fields': {
                                # Sometimes month and day are included, e.g. '"2015-08-28"'
                                'year_start': int(self.object.split('^^')[0].strip('"').split('-')[0]),
                            }
                        }
                    }
                case "estEnd":
                    return {
                        'variant': {
                            'document_id': self.subject_id,
                            'fields': {
                                # Sometimes month and day are included, e.g. '"2015-08-28"'
                                'year_end': int(self.object.split('^^')[0].strip('"').split('-')[0]),
                            }
                        }
                    }
                case "altLabel":
                    toponym_id = self.object.split('/')[-1]
                    return {
                        'place': {
                            'document_id': self.subject_id,
                            'fields': {
                                'names': [
                                    {
                                        'toponym_id': f'variant:{toponym_id}',
                                    }
                                ],
                            }
                        },
                        'variant': {
                            'document_id': toponym_id,
                            'fields': {
                                'place': self.subject_id,
                            }
                        }
                    }
                case _:  # prefLabel, prefLabelGVP
                    toponym_id = self.object.split('/')[-1]
                    return {
                        'place': {
                            'document_id': self.subject_id,
                            'fields': {
                                'names': [
                                    {
                                        'toponym_id': f'variant:{toponym_id}',
                                        'is_preferred': 2 if self.predicate == "prefLabelGVP" else 1,
                                    }
                                ],
                            }
                        },
                        'variant': {
                            'document_id': toponym_id,
                            'fields': {
                                'place': self.subject_id,
                            }
                        }
                    }
        except Exception as e:
            logger.exception(f"Exception during triple processing: {str(e)}", exc_info=True)

    def get(self, key, default=None):
        """
        Mimics dictionary .get() behaviour for the processed result.
        """
        return self.processed.get(key, default)
