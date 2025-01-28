import logging
from typing import List, Dict, Any

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
        ]
        self.url_transformers = {
            "http://dbpedia.org/resource/": {
                "uri": lambda url: f"dbp:{url.split('/')[-1]}",
            },
            "http://sws.geonames.org/": {
                "uri": lambda url: f"gn:{url.split('/')[-1]}",
            },
            "http://id.loc.gov/rwo/agents/": {
                "uri": lambda url: f"loc:{url.split('/')[-1]}",
            },
            "http://vocab.getty.edu/tgn/": {
                "uri": lambda url: f"tgn:{url.split('/')[-1].removesuffix('-place')}",
            },
            "http://www.viaf.org/viaf/": {
                "uri": lambda url: f"viaf:{url.split('/')[-1]}",
            },
            "http://www.wikidata.org/entity/": {
                "uri": lambda url: f"wd:{url.split('/')[-1]}",
            },
        }
        self.uris = set()
        self.links = []

    def _check_url(self, url: str) -> None:
        if any(url.startswith(prefix) for prefix in self.ignore_urls):
            return

        for prefix, transformers in self.url_transformers.items():
            if url.startswith(prefix):
                self.uris.add(transformers["uri"](url))
                break
        else:
            logger.warning(f"Unmatched URL: {url}")

    def process(self) -> List[Dict[str, Any]]:

        # Populate self.uris using self.linkfacets from self.graph
        logger.info(f"Processing graph: {self.graph}")
        for item in self.graph:
            for facet in self.linkfacets:
                # Check if the facet exists in the item and extract the URIs
                if (mads_facet := f"madsrdf:{facet}") in item:
                    logger.info(f"Processing facet: {mads_facet}")
                    facet_value = item[mads_facet]
                    if isinstance(facet_value, dict):
                        facet_value = [facet_value]
                    for value in facet_value:
                        logger.info(f"Processing value: {value}")
                        if isinstance(value, dict) and "@id" in value:
                            self._check_url(value["@id"])

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

        if self.links:
            logger.info(f"Processed links: {self.links}")
        return self.links
