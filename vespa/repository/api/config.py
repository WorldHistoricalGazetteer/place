# /config.py

import os

# Vespa container hosts
host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query-container-0.vespa-internal.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed-container-0.vespa-internal.vespa.svc.cluster.local:8080"),
}