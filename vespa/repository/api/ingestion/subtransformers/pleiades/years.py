from typing import List, Dict, Any


class YearsProcessor:
    def __init__(self, names: List[Dict[str, Any]], locations: List[Dict[str, Any]]):
        """
        :param names: List of name dictionaries containing (inter alia) 'start', and 'end'.
        :param locations: List of location dictionaries containing (inter alia) 'start', and 'end'.
        """
        self.names = names
        self.locations = locations

    def process(self) -> dict:
        start_year = min(
            (item["start"] for item in self.names + self.locations if "start" in item and item["start"] is not None),
            default=None
        )

        end_year = max(
            (item["end"] for item in self.names + self.locations if "end" in item and item["end"] is not None),
            default=None
        )

        return {
            **({"year_start": start_year} if start_year else {}),
            **({"year_end": end_year} if end_year else {}),
        }
