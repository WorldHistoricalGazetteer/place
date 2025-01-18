import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class LinksProcessor:
    def __init__(self, document_id, record_id, place_links: List[Dict[str, Any]]):
        """
        :param document_id: The unique ID of the document (place).
        :param record_id: The unique ID of the feature in the source.
        :param place_links: List of Pleiades place connection types (see https://pleiades.stoa.org/vocabularies/relationship-types).


        ########### Source Metadata ###########

        field source type string {
            # Origin or authority for this link (e.g., a specific gazetteer, database, dataset, or WHG User).
            indexing: attribute | summary
            attribute: fast-search
        }

        field record_id type string {
            # A unique identifier for the link within the source.
            indexing: attribute | summary
            attribute: fast-search
            match {
                exact
                exact-terminator: "@@"
            }
        }

        ########### Core Link Data ###########

        field place_id type string {
            # The ID of the place this link relates to.
            indexing: attribute | summary
            attribute: fast-search
            match {
                exact
                exact-terminator: "@@"
            }
        }

        field predicate type string {
            # The nature of the link (e.g., "has_population", "was_capital_of").
            # Ideally a URL, but may be a `label` from the `connection` schema, a controlled vocabulary for linking
            # places (e.g., "coextensive with" or "predecessor of").
            indexing: attribute | summary
            attribute: fast-search
            match {
                exact
                exact-terminator: "@@"
            }
        }

        field object type string {
            # The value of the link (e.g., ideally a URL, or "10000" for population or "Roman Empire" for a polity).
            # In the case of a `connection` to another place, this should be the WHG Vespa ID of the linked place
            # if known, or a CURIE (e.g., "pleiades:265876") if not.
            indexing: attribute | summary
            attribute: fast-search
            match {
                exact
                exact-terminator: "@@"
            }
        }

        ########### Temporal Fields ###########

        field year_start type int {
            # Start year for the validity of this link.
            indexing: attribute | summary
            attribute: fast-search
        }

        field year_end type int {
            # End year for the validity of this link.
            indexing: attribute | summary
            attribute: fast-search
        }

        ########### Additional Metadata ###########

        field confidence type float {
            # A confidence score (e.g., 0.0 to 1.0) indicating the certainty of the link.
            indexing: attribute | summary
        }

        field notes type string {
            # Additional information or context about the link.
            indexing: summary
        }

        """
        self.document_id = document_id
        self.record_id = record_id
        self.place_links = place_links
        self.certainty_map = {
            "certain": 1.0,
            "less-certain": 0.667,
            "uncertain": 0.333,
        }
        logger.info(f"Processing Pleiades place links: {place_links}")

    def process(self) -> List[Dict[str, Any]]:
        links = []
        for link in self.place_links:
            links.append({
                "source": "pleiades",
                "record_id": link.get("id"), # Pleiades connection ID
                "place_curie": f"pleiades:{self.record_id}",
                "place_id": self.document_id,
                "predicate": link.get("connectionTypeURI"),
                "object": f"pleiades:{link.get('connectsTo')}",
                **({"year_start": link.get("start")} if "start" in link else {}),
                **({"year_end": link.get("end")} if "end" in link else {}),
                **({"confidence": self.certainty_map.get(link.get("associationCertainty"))} if "associationCertainty" in link else {}),
                **({"notes": link.get("description")} if "description" in link else {}),
            })

        logger.info(f"Processed links: {links}")
        return links
