import logging
import re
from typing import List, Dict, Any

from ...namespace import namespaces

logger = logging.getLogger(__name__)


class LinksProcessor:
    def __init__(self, graph: List[Dict[str, Any]]):
        self.graph = graph
        self.linkfacets = [
            "hasExactExternalAuthority",
            "hasCloseExternalAuthority",
            "identifiesRWO",
        ]
        self.ignore_urls = [
            "http://viaf.org/viaf/sourceID/",
            "http://musicbrainz.org/",
            "https://musicbrainz.org/",
            "http://id.loc.gov/authorities/",
            "http://id.agrisemantics.org/gacs/", # Seems defunct as of 2025-01-28
            "http://data.ordnancesurvey.co.uk/id/", # Defunct as of 2025-01-28
            "http://linked-web-apis.fit.cvut.cz/", # Defunct as of 2025-01-28
            "https://orcid.org/",  # These are not place URIs
            "https://data.cerl.org/thesaurus/",  # These are not place URIs
            "http://thesaurus.cerl.org/",  # These are not place URIs
            "http://vocab.getty.edu/ulan",
            "http://www.omegawiki.org",  # Seems defunct as of 2025-01-28
            "http://gadm.geovocab.org/",  # Seems defunct as of 2025-01-28
            "http://data.cervantesvirtual.com/person/",  # These are not place URIs
        ]
        self.uris = set()
        self.links = []

    def _check_url(self, url: str) -> None:
        if any(url.startswith(prefix) for prefix in self.ignore_urls):
            # logger.info(f"Ignoring URL: {url}")
            return

        for namespace, transformer in namespaces.items():
            match = re.search(transformer["match"], url)
            if match:
                if not namespace == "loc":
                    logger.info(f"{url} -> {namespace}:{match.group('id')}")
                self.uris.add(f"{namespace}:{match.group('id')}")
                break
        else:
            logger.warning(f"Unmatched URL: {url}")

    def process(self) -> List[Dict[str, Any]]:

        # Populate self.uris using self.linkfacets from self.graph
        for item in self.graph:
            for facet in self.linkfacets:
                # Check if the facet exists in the item and extract the URIs
                if (mads_facet := f"madsrdf:{facet}") in item:
                    facet_value = item[mads_facet]
                    if isinstance(facet_value, dict):
                        facet_value = [facet_value]
                    for value in facet_value:
                        if isinstance(value, dict) and "@id" in value:
                            self._check_url(value["@id"])

        # logger.info(f"Processed URIs: {self.uris}")

        # Generate a link for every unique combination of self.uris (no symmetrical links)
        seen_pairs = set()  # Track pairs to avoid duplicates
        self.links.extend([
            {
                "place_curie": x,
                "predicate": "owl:sameAs",
                "object": y,
            }
            for x in self.uris
            for y in self.uris
            if x != y and (x, y) not in seen_pairs and not seen_pairs.add((x, y))
        ])

        # if self.links:
        #     logger.info(f"Processed links: {self.links}")
        return self.links
