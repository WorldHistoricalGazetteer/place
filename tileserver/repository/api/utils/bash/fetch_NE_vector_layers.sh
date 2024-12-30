#!/bin/bash

# Set the data folder path
data_folder="/data/k8s/tileserver/data/natural-earth"
# Make the data folder if it doesn't exist
mkdir -p "$data_folder"
cd "$data_folder"

git init
git config --global --add safe.directory "$data_folder"
git remote add origin https://github.com/nvkelso/natural-earth-vector.git
git config core.sparseCheckout true
echo "/geojson/" > .git/info/sparse-checkout
git pull origin master
rm -rf .git

# Create array of geojson files to be labelled
geojson_to_label=(
  "ne_10m_geography_regions_polys.geojson" "combine" "0-2"
  "ne_10m_admin_0_countries.geojson" "largest" "1-6"
  "ne_10m_admin_1_states_provinces.geojson" "largest" ""
)

# Loop through the array and label the geojson files
for ((i=0; i<${#geojson_to_label[@]}; i+=3)); do
  geojson_file="${geojson_to_label[i]}"
  style="${geojson_to_label[i+1]}"
  if [ -n "${geojson_to_label[i+2]}" ]; then
    zoom_range="--include-minzoom=${geojson_to_label[i+2]}"
  else
    zoom_range=""
  fi

  # Depends on old version of geojson-polygon-labels:
  # npm install -g geojson-polygon-labels@1.5.0
  geojson-polygon-labels --label polylabel --style "$style" $zoom_range "${data_folder}/geojson/${geojson_file}" > "${data_folder}/geojson/${geojson_file%.geojson}_labels.geojson"
done

