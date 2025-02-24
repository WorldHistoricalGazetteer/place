import requests

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"


def fetch_iso15924_from_wikidata():
    """Fetches ISO 15924 script codes and labels from Wikidata using SPARQL."""
    # SPARQL query to get ISO 15924 codes and labels
    query = """
    SELECT ?script ?iso15924 ?scriptLabel WHERE {
      ?script wdt:P506 ?iso15924.  # Get items with an ISO 15924 code
      FILTER(STRLEN(?iso15924) = 4)  # Filter for codes that are 4 letters long
      SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }
    }
    """

    # Set parameters for the SPARQL request
    params = {
        "format": "json",
        "query": query
    }

    response = requests.get(WIKIDATA_SPARQL_URL, params=params)
    response.raise_for_status()

    data = response.json()

    # Extract the script codes and labels
    script_data = {}

    for item in data["results"]["bindings"]:
        iso15924_code = item["iso15924"]["value"]
        script_name = item["scriptLabel"]["value"]
        script_data[iso15924_code] = script_name

    return script_data


def save_script_data(script_data):
    """Saves the script data as a Python dictionary in a file with one entry per line in alphabetical order."""
    with open("iso15924.py", "w", encoding="utf-8") as f:
        f.write("# ISO 15924 script codes mapping from Wikidata\n")
        f.write("ISO_15924 = {\n")

        # Sort script data alphabetically by script code
        for iso15924_code, script_name in sorted(script_data.items()):
            # Escape apostrophes in the script name
            script_name_escaped = script_name.replace("'", "\\'")
            f.write(f"    '{iso15924_code}': '{script_name_escaped}',\n")

        f.write("}\n")


if __name__ == "__main__":
    try:
        iso_15924 = fetch_iso15924_from_wikidata()
        save_script_data(iso_15924)
        print("ISO 15924 script codes saved to iso15924_from_wikidata.py")
    except Exception as e:
        print(f"Error: {e}")
