import logging
from typing import List, Dict, Any

from ....gis.processor import GeometryProcessor

logger = logging.getLogger(__name__)


class LocationsProcessor:
    def __init__(self, locations: List[Dict[str, Any]]):
        """
        :param locations: List of location dictionaries.

        Example:

        "locations": [
          {
            "id": "q60$f00c56de-4bac-e259-b146-254897432868",
            "mainsnak": {
              "snaktype": "value",
              "property": "P625",
              "datatype": "globe-coordinate",
              "datavalue": {
                "value": {
                  "latitude": 40.67,
                  "longitude": -73.94,
                  "altitude": null,
                  "precision": 0.00027777777777778,
                  "globe": "http://www.wikidata.org/entity/Q2"
                },
                "type": "globecoordinate"
              }
            },
            "type": "statement",
            "rank": "normal",
            "references": [
              {
                "hash": "7eb64cf9621d34c54fd4bd040ed4b61a88c4a1a0",
                "snaks": {
                  "P143": [
                    {
                      "snaktype": "value",
                      "property": "P143",
                      "datatype": "wikibase-item",
                      "datavalue": {
                        "value": {
                          "entity-type": "item",
                          "id": "Q328",
                          "numeric-id": 328
                        },
                        "type": "wikibase-entityid"
                      }
                    }
                  ]
                },
                "snaks-order": [
                  "P143"
                ]
              }
            ]
          }
        ],
        """
        self.locations = locations

    def process(self) -> dict:
        """
        Processes the locations to generate a GeometryCollection with start and end years for each geometry.
        """

        # logger.info(f"Processing Pleiades locations: {self.locations}")

        geometry = {
            "type": "GeometryCollection",
            "geometries": [
                {
                    "type": "Point",
                    "coordinates": [
                        location["mainsnak"]["datavalue"]["value"]["longitude"],
                        location["mainsnak"]["datavalue"]["value"]["latitude"],
                    ],
                    "year_start": 2025,
                    "year_end": 2025,
                }
                for location in self.locations
            ],
        }

        return GeometryProcessor(geometry).process()
