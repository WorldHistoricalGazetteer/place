import json
import logging
import re
import unicodedata
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
        # logger.info(f"Processing Linked Art object: {linked_art_ld}")
        self.linked_art_ld = linked_art_ld
        self.id = linked_art_ld.get('id').split('/')[-1]
        self.names = []
        self.toponyms = []
        self._get_names()
        try:
            self.coordinate_string = self._get_value_from_type(linked_art_ld.get('identified_by', []), 'crm:E47_Spatial_Coordinates')
            # Add leading zeros to the coordinates where required for valid JSON, e.g. '[-.166,11.5833]' -> '[-0.166,11.5833]'
            self.coordinate_string = re.sub(r'(?<!\d)\.(\d+)', r'0.\1', self.coordinate_string)
            # Convert self.coordinate_string like '[-101.123047, 37.09024]' to a list of floats
            self.coordinates = json.loads(self.coordinate_string) if self.coordinate_string else None
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
            # Normalise Unicode (NFC to prevent decomposition issues)
            toponym = unicodedata.normalize("NFC", toponym)
            # Remove problematic invisible Unicode characters
            toponym = toponym.translate(dict.fromkeys([0x200B, 0x2060]))
            # Ensure UTF-8 encoding (ignore errors)
            toponym = toponym.encode("utf-8", "strict").decode("utf-8")

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
                    **(parse_bcp47_fields(isolanguages[0].get('id','').split('/')[-1]) if (isolanguages := name.get('language')) else {}),
                }
            })

    def process(self) -> dict:

        # logger.info(f"Processed Linked Art object: {self.id}")
        # logger.info((f"Toponym count: {len(self.toponyms)}"))

        try:
            return {
                'id': self.id,
                'place': {
                    'record_id': self.id,
                    'record_url': f'https://vocab.getty.edu/tgn/{self.id}.jsonld',

                    'names': self.names,

                    'bbox_sw_lat': (bbox_sw_lat:= self.coordinates[0]),
                    'bbox_sw_lng': (bbox_sw_lng:= self.coordinates[1]),
                    'bbox_ne_lat': bbox_sw_lat,
                    'bbox_ne_lng': bbox_sw_lng,
                    "bbox_antimeridial": False,
                    "convex_hull": (point := json.dumps(point_json := {
                        "type": "Point",
                        "coordinates": [bbox_sw_lng, bbox_sw_lat]
                    })),
                    "locations": [{"geometry": point}],
                    "representative_point": {"lat": bbox_sw_lat,
                                                 "lng": bbox_sw_lng},

                    'types': [aat.get('id').split('/')[-1] for aat in self.linked_art_ld.get('classified_as', [])],

                    **({"ccodes": [
                            meta["ISO_A2"] for result in GeometryIntersect(geometry=point_json).resolve()
                            if (meta := json.loads(result["meta"]))["ISO_A2"] != "-"
                        ]} if bbox_sw_lat and bbox_sw_lng else {}),

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
        except Exception as e:
            logger.error(f"Error processing Linked Art object: {e}", exc_info=True)
            logger.info(f"Linked Art object: {self.linked_art_ld}")
            return {}
