# /config.py

import os

namespace = os.getenv("VESPA_NAMESPACE", "vespa")

host_mapping = {
    "query": os.getenv("VESPA_QUERY_HOST",
                       "http://vespa-query.vespa.svc.cluster.local:8080"),
    "feed": os.getenv("VESPA_FEED_HOST", "http://vespa-feed.vespa.svc.cluster.local:8080"),
    "api": os.getenv("VESPA_API_HOST", "http://vespa-api.vespa.svc.cluster.local:8082"),
}

descriptions_map = {
    "austria": "Digital elevation model with 10-metre resolution over Austria, provided by data.gv.at.",
    "etopo1": "Global ocean bathymetry model with a 1 arc-minute resolution, covering the world’s oceans.",
    "eudem": "EU-DEM offers 30-metre resolution in most European countries, created from multiple European datasets.",
    "geoscience_au": "Geoscience Australia's 5-metre resolution DEM, focusing on coastal areas of South Australia, Victoria, and the Northern Territory.",
    "gmted": "Global Multi-Resolution Terrain Elevation Data at resolutions of 7.5\", 15\", and 30\", covering land globally.",
    "kartverket": "Norway’s 10-metre resolution Digital Terrain Model, managed by Kartverket.",
    "mx_lidar": "INEGI’s lidar-based continental relief data for Mexico, offering high accuracy.",
    "ned": "National Elevation Dataset with 10-metre resolution across most of the United States, excluding Alaska.",
    "ned13": "Higher-resolution 3-metre data from the US 3DEP program, available in selected areas.",
    "ned_topobathy": "3-metre resolution dataset of US coastal and water regions, part of the 3DEP initiative.",
    "nrcan_cdem": "Canadian Digital Elevation Model with variable resolutions from 20 to 400 metres depending on latitude, provided by NRCan.",
    "nzlinz": "New Zealand’s LINZ 8-metre resolution elevation model, covering the entire country.",
    "pgdc_5m": "ArcticDEM 5-metre mosaic for polar regions above 60° latitude, covering the Arctic nations.",
    "srtm": "NASA's Shuttle Radar Topography Mission dataset at 30-metre resolution, excluding high latitudes.",
    "uk_lidar": "2-metre resolution lidar dataset over the UK, provided by data.gov.uk.",
}
