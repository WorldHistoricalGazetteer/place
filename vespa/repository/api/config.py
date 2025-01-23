# /config.py

import os

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result
from vespa.application import Vespa, VespaSync

namespace = os.getenv("VESPA_NAMESPACE", "vespa")
pagination_limit = 250

host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}


class VespaExtended(Vespa):
    """
    A subclass of Vespa that adds the query_root method.
    """

    def return_last_result(retry_state):
        return retry_state.outcome.result()

    def return_none(retry_state):
        return None

    def has_errors(result):
        return bool(result.get("error"))

    def is_500_error(result):
        return result >= 500

    @retry(
        # See https://tenacity.readthedocs.io/en/latest/
        stop=stop_after_attempt(5),  # Max 5 attempts
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry_error_callback=return_last_result,
        retry=retry_if_result(has_errors)
    )
    def query_existing(self, query_body: dict, namespace: str = None, schema: str = None) -> dict:
        response = self.query(body=query_body, namespace=namespace, schema=schema)
        response_root = response.get_json().get("root", {})

        if errors := response_root.get("errors"):
            return {"error": errors}

        if response_root.get("fields", {}).get("totalCount", 0) == 0:
            return {}

        document = (
            response_root.get("children", [{}])[0]
            .get("fields", {})
        )
        return {
            "document_id": document.get("documentid", "").split("::")[-1],
            "fields": document,
        }

    @retry(
        # See https://tenacity.readthedocs.io/en/latest/
        stop=stop_after_attempt(5),  # Max 5 attempts
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry_error_callback=return_none,
        retry=retry_if_result(is_500_error)
    )
    def get_existing(self, data_id: str = None, namespace: str = None, schema: str = None) -> dict:
        response = self.get_data(
            data_id=data_id,
            namespace=namespace,
            schema=schema,
        )
        return {
            'document_id': data_id,
            'fields': response.get_json().get("fields", {})
        } if response.is_successful() else response.get_status_code()

    @retry(
        # See https://tenacity.readthedocs.io/en/latest/
        stop=stop_after_attempt(5),  # Max 5 attempts
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry_error_callback=return_none,
        retry=retry_if_result(is_500_error)
    )
    def update_existing(self, data_id: str = None, namespace: str = None, schema: str = None, fields: dict = None, create: bool = False) -> dict:
        response = self.update_data(
            data_id=data_id,
            namespace=namespace,
            schema=schema,
            fields=fields,
            create=create
        )
        return {
            'document_id': data_id,
            'fields': response.get_json().get("fields", {})
        } if response.is_successful() else response.get_status_code()


class VespaClient:
    _instances = {}

    @classmethod
    def get_instance(cls, client_type: str) -> Vespa | VespaExtended:
        """
        Get or create a Vespa client instance for the specified client type.
        """
        if client_type not in cls._instances:
            url = host_mapping.get(client_type)
            if not url:
                raise ValueError(f"No URL found for client type: {client_type}")

            client = VespaExtended(url=url)

            cls._instances[client_type] = client

        return cls._instances[client_type]

    @classmethod
    def get_url(cls, client_type):
        """
        Get the URL associated with a Vespa client.
        """
        url = host_mapping.get(client_type)
        if not url:
            raise ValueError(f"No URL found for client type: {client_type}")
        return url

    @classmethod
    def sync_context(cls, client_type):
        """
        Provide a context manager for VespaSync.
        """
        app = cls.get_instance(client_type)
        return VespaSync(app)
