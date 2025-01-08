# /config.py

import os

namespace = os.getenv("VESPA_NAMESPACE", "vespa")

host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
}

batch_feed_size = int(os.getenv("VESPA_BATCH_FEED_SIZE", 500))
