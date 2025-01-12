# /config.py

import os

from vespa.application import Vespa, VespaSync

namespace = os.getenv("VESPA_NAMESPACE", "vespa")

host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}


class VespaClient:
    _instances = {}

    @classmethod
    def get_instance(cls, client_type):
        if client_type not in cls._instances:
            url = host_mapping[client_type]
            cls._instances[client_type] = Vespa(url=url)
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
