import pickle
import json
import requests
import gzip
from io import BytesIO
from shapely.geometry import shape
import os

bounds_map = {}
geometry_map = {}
properties_map = {}
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

# Fetch GeoJSON data from the S3 URL
geojson_url = "https://s3.amazonaws.com/elevation-tiles-prod/docs/footprints.geojson.gz"
response = requests.get(geojson_url)

# Decompress the gzipped content and load JSON
with gzip.GzipFile(fileobj=BytesIO(response.content)) as f:
    geojson_data = json.load(f)

# Filter out only resolution and source properties
i = 0
for feature in geojson_data['features']:

    if feature['geometry']['coordinates'] == []:
        print(f"Skipping feature with empty coordinates", feature)
        continue

    feature['properties'] = {key: feature['properties'][key] for key in ['resolution', 'source']}
    polygon = shape(feature['geometry'])
    bounds = polygon.bounds
    i += 1
    geometry_map[i] = polygon
    properties_map[i] = feature['properties']
    # Split if the bounding box crosses the antimeridian
    if bounds[0] > bounds[2]:
        bounds_map[i] = [bounds[0], bounds[1], 180, bounds[3]]
        i += 1
        geometry_map[i] = polygon
        properties_map[i] = feature['properties']
        bounds_map[i] = [-180, bounds[1], bounds[2], bounds[3]]
    else:
        bounds_map[i] = bounds

# Ensure the directory exists
os.makedirs('./data', exist_ok=True)

# Save the index, properties_map, and descriptions_map to a single pickle file
with open("./data/terrarium-data.pkl", "wb") as f:
    pickle.dump({
        'bounds': bounds_map,
        'geometry': geometry_map,
        'properties': properties_map,
        'descriptions': descriptions_map
    }, f)
