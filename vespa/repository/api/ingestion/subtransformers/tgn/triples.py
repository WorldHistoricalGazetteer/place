import logging

import httpx

logger = logging.getLogger(__name__)


class TriplesProcessor:
    def __init__(self, data: dict):
        """
        :param data: A dictionary containing 'subject', 'predicate', and 'object' keys.
        """
        try:
            self.data = data
            self.id = data.get("subject", "").split('/')[-1]  # Extract ID
            self.fields = {}
            self.names = []
            self.links = []
        except Exception as e:
            logger.exception(f"Exception during initialization: {str(e)}", exc_info=True)

    async def fetch_jsonld(self):
        """Fetch JSON-LD from Getty TGN."""
        url = f"https://vocab.getty.edu/tgn/{self.id}.jsonld"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching {url}: {str(e)}")
        except Exception as e:
            logger.exception(f"Unexpected error fetching {url}: {str(e)}", exc_info=True)
        return None  # Return None if there's an error

    async def process(self):
        """Process the JSON-LD data."""
        try:
            jsonld = await self.fetch_jsonld()
            if jsonld:
                self.parse_jsonld(jsonld)
        except Exception as e:
            logger.exception(f"Exception during triple processing {self.data}: {str(e)}", exc_info=True)

    def parse_jsonld(self, jsonld: dict):
        """Extract relevant information from the JSON-LD response."""
        try:
            for item in jsonld.get('@graph', []):
                if 'prefLabel' in item:
                    self.names.append(item['prefLabel'])
                if 'sameAs' in item:
                    self.links.append(item['sameAs'])

            self.fields = {
                "id": self.id,
                "names": self.names,
                "links": self.links,
            }
        except Exception as e:
            logger.exception(f"Error parsing JSON-LD data: {str(e)}", exc_info=True)
