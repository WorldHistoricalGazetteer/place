# This script extracts named places and features from the OpenStreetMap planet file and exports them as a GeoJSON sequence file.

osmium tags-filter \
  --fsync \
  -o /data/k8s/vespa-ingestion/osm-names.pbf \
  -O \
  --progress \
  /data/k8s/vespa-ingestion/planet-latest.osm.pbf \
  name

osmium tags-filter \
  --fsync \
  -o /data/k8s/vespa-ingestion/osm-names-places-etc.pbf \
  -O \
  --progress \
  /data/k8s/vespa-ingestion/osm-names.pbf \
  geological historic place water waterway

osmium export \
  -i dense_file_array \
  -f geojsonseq \
  --fsync \
  -o /data/k8s/vespa-ingestion/osm.geojsonseq \
  -O \
  --progress \
  /data/k8s/vespa-ingestion/osm-names-places-etc.pbf

# Remove the intermediate PBF files
rm /data/k8s/vespa-ingestion/osm-names.pbf /data/k8s/vespa-ingestion/osm-names-places-etc.pbf