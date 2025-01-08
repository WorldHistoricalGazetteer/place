# /system/status.py

from typing import Dict

import httpx

from ..config import host_mapping


def extract_status(data: Dict) -> Dict:
    """
    Extract relevant status details from the Vespa ApplicationStatus response.
    """
    try:
        version = data["application"]["vespa"]["version"]
        meta_date = data["application"]["meta"]["date"]
        generation = data["application"]["meta"]["generation"]
        return {
            "vespa_version": version,
            "last_updated": meta_date,
            "generation": generation,
        }
    except KeyError as e:
        raise ValueError(f"Missing key in response: {e}")


async def get_vespa_status() -> Dict:
    """
    Fetches the status of the Vespa containers.
    Returns a dictionary of statuses.
    """
    async with httpx.AsyncClient() as client:
        statuses = {}
        try:
            for host_type, host_url in host_mapping.items():
                response = await client.get(f"{host_url}/ApplicationStatus")
                response.raise_for_status()
                data = response.json()
                statuses[f"{host_type}"] = extract_status(data)
        except httpx.RequestError as e:
            raise Exception(f"Error contacting Vespa containers: {str(e)}")
        except ValueError as e:
            raise Exception(f"Invalid response structure: {str(e)}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {str(e)}")

    return statuses
