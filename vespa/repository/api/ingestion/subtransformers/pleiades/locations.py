from typing import List, Dict, Any

from ....gis.processor import GeometryProcessor


class LocationsProcessor:
    def __init__(self, locations: List[Dict[str, Any]]):
        """
        :param locations: List of location dictionaries containing (inter alia) 'geometry', 'start', and 'end'.
        """
        self.locations = locations

    def process(self) -> dict:
        """
        Processes the locations to generate a GeometryCollection with start and end years for each geometry.
        """
        geometry = {
            "type": "GeometryCollection",
            "geometries": [
                {
                    **location["geometry"],
                    "start": location.get("start"),
                    "end": location.get("end"),
                }
                for location in self.locations
            ],
        }

        return GeometryProcessor(geometry).process()
