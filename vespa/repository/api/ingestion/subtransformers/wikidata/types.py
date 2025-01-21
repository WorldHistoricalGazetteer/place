import logging
from typing import List, Dict, Any

from ....config import VespaClient

logger = logging.getLogger(__name__)


class TypesProcessor:
    def __init__(self, instance_of: List[Dict[str, Any]], geonames_id: List[Dict[str, Any]]):
        """
        :param instance_of: List of 'instance of' dictionaries.
        :param geonames_id: List of 'GeoNames ID' dictionaries.

        Returns:
        {
            "types": List of AAT types,
            "classes": List of GeoNames feature classes
        }
        """
        self.instance_of = instance_of
        self.geonames_id = geonames_id

    def process(self) -> Dict[str, Any]:

        types = []
        classes = []

        for instance in self.instance_of:
            instance_of = instance.get("mainsnak", {}).get("datavalue", {}).get("value")
            if instance_of:
                types.append(f"wd:{instance_of}")

        for geoname in self.geonames_id:
            # Use Vespa query on gn: namespace to get GeoNames class
            record_id = geoname.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not record_id:
                continue
            try:
                with VespaClient.sync_context("feed") as sync_app:
                    yql = f'select * from place where record_id = "{record_id}"'
                    response = sync_app.query(
                        yql,
                        namespace="gn",
                        schema="place",
                    ).json

                    if "error" in response:
                        logger.error(f"Error in Vespa query for record_id {record_id}: {response['error']}")
                        continue

                    feature_class = (
                        response.get("root", {})
                        .get("children", [{}])[0]
                        .get("fields", {})
                        .get("classes", [])
                    )
                    if feature_class:
                        classes.extend(feature_class)
            except Exception as e:
                logger.exception(f"Exception during Vespa query for record_id {record_id}: {str(e)}")

        return {
            **({"types": types} if types else {}),
            **({"classes": classes} if classes else {}),
        }
