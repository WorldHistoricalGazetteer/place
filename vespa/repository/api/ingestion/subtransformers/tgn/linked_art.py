import json
import logging
from typing import Dict, Any

from ....bcp_47.bcp_47 import parse_bcp47_fields
from ....gis.intersections import GeometryIntersect
from ....utils import get_uuid

logger = logging.getLogger(__name__)


class LinkedArtProcessor:
    def __init__(self, linked_art_ld: Dict[str, Any]):
        """
        :param linked_art_ld: The Linked Art JSON-LD object.
        """
        self.linked_art_ld = linked_art_ld
        self.id = linked_art_ld.get('id').split('/')[-1]
        self.names = []
        self.toponyms = []
        self._get_names()
        try:
            self.coordinate_string = self._get_value_from_type(linked_art_ld.get('identified_by', []), 'crm:E47_Spatial_Coordinates')
            self.coordinates = [float(x) for x in self.coordinate_string.split(',') if x] if self.coordinate_string else None
            # Force error if there are not exactly two coordinates
            if self.coordinates and len(self.coordinates) != 2:
                raise ValueError(f"Invalid point coordinates: {self.coordinates}")
        except Exception as e:
            logger.error(f"Error in LinkedArtProcessor: {e}", exc_info=True)
            self.coordinates = None

    def _get_value_from_type(self, list: list, type: str) -> str:
        return next((x.get('value') for x in list if x.get('type') == type), None)

    def _get_names(self):

        for name in filter(lambda name_ld: name_ld.get('type') == 'Name', self.linked_art_ld.get('identified_by', [])):
            toponym = name.get('content').strip()
            preferred = any(cls.get('id', '') == 'http://vocab.getty.edu/aat/300404670' for cls in name.get('classified_as', []))

            self.names.append({
                'toponym_id': (toponym_id := name.get('id').split('/')[-1]),
                'year_start': 2025,
                'year_end': 2025,
                **({'is_preferred': 1} if preferred else {}),
            })
            self.toponyms.append({
                'id': toponym_id,
                'fields': {
                    'is_staging': True,
                    'name_strict': toponym,
                    'name': toponym,
                    'places': [self.id],
                    **(parse_bcp47_fields(isolanguage) if (isolanguage := name.get('language')) else {}),
                }
            })

    def process(self) -> dict:

        return {
            'id': self.id,
            'place': {
                'record_id': self.id,
                'record_url': f'https://vocab.getty.edu/tgn/{self.id}.jsonld',

                'names': self.names,

                **({"bbox_sw_lat": bbox_sw_lat} if (bbox_sw_lat := self.coordinates[0]) else {}),
                **({"bbox_sw_lng": bbox_sw_lng} if (bbox_sw_lng := self.coordinates[1]) else {}),
                **({"bbox_ne_lat": bbox_sw_lat} if bbox_sw_lat else {}),
                **({"bbox_ne_lng": bbox_sw_lng} if bbox_sw_lng else {}),
                "bbox_antimeridial": False,
                **({"convex_hull": point} if (point := json.dumps((point_json := {
                    "type": "Point",
                    "coordinates": [bbox_sw_lng, bbox_sw_lat]
                })) if bbox_sw_lng and bbox_sw_lat else None) else {}),
                **({"locations": [{"geometry": point}]} if point else {}),
                **({"representative_point": {"lat": bbox_sw_lat,
                                             "lng": bbox_sw_lng}} if bbox_sw_lat and bbox_sw_lng else {}),

                'types': [aat.get('id').split('/')[-1] for aat in self.linked_art_ld.get('classified_as', [])],

                **({"country_codes": GeometryIntersect(geometry=point_json).resolve()} if bbox_sw_lat and bbox_sw_lng else {}),
            },
            'toponyms': self.toponyms,
            'links': [
                # {
                #     "place_id": self.id,
                #     "predicate": None,
                #     "object": None,
                # } for link in self.linked_art_ld.get('see_also', [])
            ],
        }
