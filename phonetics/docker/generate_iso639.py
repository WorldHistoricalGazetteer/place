import csv
import json
import requests

ISO639_URL = "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab"
OUTPUT_FILE = "iso639.py"


def fetch_iso639():
    """Fetches ISO 639-3 data and returns a mapping of ISO 639-2 → ISO 639-3."""
    response = requests.get(ISO639_URL)
    response.raise_for_status()

    mapping = {}
    lines = response.text.splitlines()
    reader = csv.DictReader(lines, delimiter="\t")

    # Print headers to debug
    print("Headers:", reader.fieldnames)

    for row in reader:
        # Print the first few rows to inspect data
        print(row)

        if row.get("Part1"):
            mapping[row["Part1"]] = {"639-3": row["Id"], "label": row["Ref_Name"]}

    return mapping


def save_mapping(mapping):
    """Saves the mapping as a Python dictionary in `iso639.py`."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# ISO 639-2 to ISO 639-3 mapping\n")
        f.write("ISO_639_2_TO_3 = ")
        f.write(json.dumps(mapping, indent=4, ensure_ascii=False))
        f.write("\n")


if __name__ == "__main__":
    try:
        mapping = fetch_iso639()
        save_mapping(mapping)
        print(f"ISO 639 mapping saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error: {e}")
