import logging
from typing import List, Dict, Any

from ....gis.processor import GeometryProcessor

logger = logging.getLogger(__name__)


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

        # logger.info(f"Processing Pleiades locations: {self.locations}")

        geometry = {
            "type": "GeometryCollection",
            "geometries": [
                {
                    **location["geometry"],
                    "start": location.get("start"),
                    "end": location.get("end"),
                }
                for location in self.locations
                if location.get("geometry") and isinstance(location["geometry"], dict)
            ],
        }

        return GeometryProcessor(geometry).process()
