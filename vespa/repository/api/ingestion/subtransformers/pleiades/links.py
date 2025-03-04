import logging
from typing import List, Dict, Any

from ....utils import get_uuid

logger = logging.getLogger(__name__)


class LinksProcessor:
    def __init__(self, document_id, record_id, place_links: List[Dict[str, Any]]):
        """
        :param document_id: The unique ID of the document (place).
        :param record_id: The unique ID of the feature in the source.
        :param place_links: List of Pleiades place connection types (see https://pleiades.stoa.org/vocabularies/relationship-types).
        """
        self.document_id = document_id
        self.record_id = record_id
        self.place_links = place_links
        self.certainty_map = {
            "certain": 1.0,
            "less-certain": 0.667,
            "uncertain": 0.333,
        }
        # logger.info(f"Processing Pleiades place links: {place_links}")

    def process(self) -> List[Dict[str, Any]]:
        links = []
        for link in self.place_links:
            links.append(
                {
                    "id": get_uuid(),
                    "fields": {
                        "record_id": link.get("id"),  # Pleiades connection ID
                        "place_curie": f"pleiades:{self.record_id}",
                        "place_id": self.document_id,
                        "predicate": link.get("connectionTypeURI"),
                        "object": f"pleiades:{link.get('connectsTo')}",
                        **({"year_start": link.get("start")} if "start" in link else {}),
                        **({"year_end": link.get("end")} if "end" in link else {}),
                        **({"confidence": self.certainty_map.get(
                            link.get("associationCertainty"))} if "associationCertainty" in link else {}),
                        **({"notes": link.get("description")} if "description" in link else {}),
                    }
                }
            )

        # logger.info(f"Processed links: {links}")
        return links
