#!/bin/bash

# Directory containing the templates
TEMPLATES_DIR="prometheus-grafana/prometheus/templates"

# Process each YAML file in the directory
for file in "$TEMPLATES_DIR"/*.yaml; do
  if [[ -f "$file" ]]; then
    echo "Processing file: $file"

    sed -i -E 's/\{\{(([^}]|}[^}])*)\}\}/\{\{ "{{" \}\}\1\{\{ "}}" \}\}/g' "$file"
  fi
done

echo "Replacement complete."
