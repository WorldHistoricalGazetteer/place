import requests
import json

# SPARQL query template
SPARQL_TEMPLATE = """
SELECT (STRAFTER(STR(?x), "/aat/") AS ?id) ?label
WHERE {{
  ?x gvp:broaderExtended aat:{aat_id};
     skos:inScheme aat:;
     gvp:prefLabelGVP/xl:literalForm ?l.
  BIND(STR(?l) AS ?label)
}}
"""

# SPARQL endpoint
SPARQL_URL = "https://vocab.getty.edu/sparql.json"


# Function to fetch descendants for an AAT ID
def fetch_descendants(aat_id):
    query = SPARQL_TEMPLATE.format(aat_id=aat_id)
    response = requests.get(SPARQL_URL, params={"query": query})
    response.raise_for_status()
    results = response.json().get("results", {}).get("bindings", [])

    # Parse results into a list of dictionaries
    return [{"id": result["id"]["value"], "label": result["label"]["value"]} for result in results]


AAT_Feature_Classes = {
    "A": {
        "label": "Administrative Boundary",
        "aat": [
            {
                "label": "administrative districts",
                "id": "300000707",
                "descendants": []
            },
            {
                "label": "political divisions",
                "id": "300236157",
                "descendants": []
            },
        ],
    },
    "H": {
        "label": "Hydrographic",
        "aat": [
            {
                "label": "bodies of water (natural)",
                "id": "300266059",
                "descendants": []
            },
            {
                "label": "hydraulic structures",
                "id": "300006073",
                "descendants": []
            },
        ],
    },
    "L": {
        "label": "Area",
        "aat": [
            {
                "label": "regions (geographic)",
                "id": "300182722",
                "descendants": []
            },
            {
                "label": "landscapes (environments)",
                "id": "300008626",
                "descendants": []
            },
        ],
    },
    "P": {
        "label": "Populated Place",
        "aat": [
            {
                "label": "inhabited places",
                "id": "300008347",
                "descendants": []
            },
        ],
    },
    "R": {
        "label": "Road / Railroad",
        "aat": [
            {
                "label": "roads",
                "id": "300008217",
                "descendants": []
            },
            {
                "label": "transit systems (infrastructure)",
                "id": "300008556",
                "descendants": []
            },
        ],
    },
    "S": {
        "label": "Spot",
        "aat": [
            {
                "label": "single built works (built environment)",
                "id": "300004790",
                "descendants": []
            },
        ],
    },
    "T": {
        "label": "Hypsographic",
        "aat": [
            {
                "label": "landforms (terrestrial)",
                "id": "300266060",
                "descendants": []
            },
        ],
    },
    "U": {
        "label": "Undersea",
        "aat": [
            {
                "label": "undersea landforms",
                "id": "300387581",
                "descendants": []
            },
        ],
    },
    "V": {
        "label": "Vegetation",
        "aat": [
            {
                "label": "vegetation",
                "id": "300266061",
                "descendants": []
            },
        ],
    },
}

# Create a lookup dictionary
AAT_Lookup = {}

# Populate descendants for each AAT entry and build the lookup dictionary
for feature_class_key, feature_class in AAT_Feature_Classes.items():
    for aat_entry in feature_class["aat"]:
        print(f"Fetching descendants for AAT ID: {aat_entry['id']}...")
        descendants = fetch_descendants(aat_entry["id"])
        aat_entry["descendants"] = descendants

        # Add the base AAT entry to the lookup
        AAT_Lookup[aat_entry["id"]] = {
            "feature_class": feature_class_key,
            "label": feature_class["label"],
            "aat_label": aat_entry["label"]
        }

        # Add all descendant AAT entries to the lookup
        for descendant in descendants:
            AAT_Lookup[descendant["id"]] = {
                "feature_class": feature_class_key,
                "label": feature_class["label"],
                "aat_label": descendant["label"]
            }

# Save the dictionaries to files
with open("/data/k8s/vespa-ingestion/AAT_Feature_Classes.json", "w", encoding="utf-8") as f:
    json.dump(AAT_Feature_Classes, f, indent=4, ensure_ascii=False)

with open("/data/k8s/vespa-ingestion/AAT_Lookup.json", "w", encoding="utf-8") as f:
    json.dump(AAT_Lookup, f, indent=4, ensure_ascii=False)

print("Dictionaries saved to AAT_Feature_Classes.json and AAT_Lookup.json.")
