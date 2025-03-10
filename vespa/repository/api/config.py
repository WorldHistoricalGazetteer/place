# /config.py
import logging
import os

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_result, retry_if_not_result
from vespa.application import Vespa, VespaSync

logger = logging.getLogger(__name__)

namespace = os.getenv("VESPA_NAMESPACE", "vespa")
pagination_limit = 250

host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}

class VespaSyncExtended(VespaSync):
    """
    A subclass of VespaSync that adds the methods from VespaExtended.
    """
    def __init__(self, app, pool_maxsize=20, **kwargs):
        if not isinstance(app, VespaExtended):
            raise TypeError("VespaSyncExtended expects an instance of VespaExtended")
        # Increase the pool size to 20 (see https://pyvespa.readthedocs.io/en/stable/reference-api.html#vespasync)
        super().__init__(app, pool_maxsize=pool_maxsize, **kwargs)

    def __getattr__(self, name):
        """
        Delegate method calls to the underlying VespaExtended instance.
        """
        attr = getattr(self.app, name, None)
        if attr is None:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        return attr

    def get_existing(self, data_id: str = None, namespace: str = None, schema: str = None) -> dict:
        return self.app.get_existing(data_id=data_id, namespace=namespace, schema=schema)

    def update_existing(self, *args, **kwargs) -> dict:
        return self.app.update_existing(*args, **kwargs)

    def feed_existing(self, *args, **kwargs) -> dict:
        return self.app.feed_existing(*args, **kwargs)

    def query_existing(self, *args, **kwargs) -> dict:
        return self.app.query_existing(*args, **kwargs)


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

    def status_code_ok(result):
        return (status_code := result.get('status_code')) and status_code < 500

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
        retry=retry_if_not_result(status_code_ok)
    )
    def get_existing(self, data_id: str = None, namespace: str = None, schema: str = None) -> dict:
        response = self.get_data(
            data_id=data_id,
            namespace=namespace,
            schema=schema,
        )
        return {
            'document_id': data_id,
            'fields': response.get_json().get("fields", {}),
            'status_code': response.get_status_code(),
        }

    @retry(
        # See https://tenacity.readthedocs.io/en/latest/
        stop=stop_after_attempt(5),  # Max 5 attempts
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry_error_callback=return_none,
        retry=retry_if_not_result(status_code_ok)
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
            'fields': response.get_json().get("fields", {}),
            'status_code': response.get_status_code(),
        }

    @retry(
        # See https://tenacity.readthedocs.io/en/latest/
        stop=stop_after_attempt(5),  # Max 5 attempts
        wait=wait_exponential(multiplier=1, min=1, max=16),
        retry_error_callback=return_none,
        retry=retry_if_not_result(status_code_ok)
    )
    def feed_existing(self, data_id: str = None, namespace: str = None, schema: str = None, fields: dict = None, create: bool = False) -> dict:
        response = self.feed_data_point(
            data_id=data_id,
            namespace=namespace,
            schema=schema,
            fields=fields,
            create=create
        )
        return {
            'document_id': data_id,
            'fields': response.get_json().get("fields", {}),
            'status_code': response.get_status_code(),
        }


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
    def sync_context(cls, client_type, asynchronous=False):
        """
        Provide a context manager for VespaSync.
        """
        app = cls.get_instance(client_type)
        if not isinstance(app, VespaExtended):
            raise TypeError("Expected VespaExtended instance")
        if asynchronous:
            return app
        return VespaSyncExtended(app)
