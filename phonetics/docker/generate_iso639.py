import csv
import json
import requests

ISO639_URL = "https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab"
OUTPUT_FILE = "iso639.py"


def fetch_iso639():
    """Fetches ISO 639-3 data and generates two mappings:
    - ISO_639_3: Full metadata for each ISO 639-3 code.
    - ISO_639_1_TO_3: Direct mapping from ISO 639-1 to ISO 639-3.
    """
    response = requests.get(ISO639_URL)
    response.raise_for_status()

    iso_639_3 = {}
    iso_639_1_to_3 = {}
    lines = response.text.splitlines()
    reader = csv.DictReader(lines, delimiter="\t")

    # Print headers to debug
    print("Headers:", reader.fieldnames)

    for row in reader:
        # Print row to inspect data
        print(row)

        entry = {key.lower(): (value.strip() if value else None) for key, value in row.items() if value.strip() and not key == "Id"}
        iso_639_3[row["Id"]] = entry if entry else None

        if entry.get("part1"):
            iso_639_1_to_3[entry["part1"]] = {"639-3": row["Id"], "ref_name": entry["ref_name"]}

    return iso_639_3, iso_639_1_to_3


def save_mapping(iso_639_3, iso_639_1_to_3):
    """Saves the mapping as a Python dictionary in `iso639.py`."""

    # Dictionaries for Scope and Language_Type with label and description
    SCOPE_DESCRIPTIONS = {
        "I": {
            "label": "Individual language",
            "description": "A single language (e.g., English, Spanish)"
        },
        "M": {
            "label": "Macrolanguage",
            "description": "A group of languages that share a common name and may or may not be mutually intelligible (e.g., Arabic, Chinese)"
        },
        "C": {
            "label": "Collective",
            "description": "A collective term for multiple languages grouped together (e.g., sign languages)"
        },
        "S": {
            "label": "Special",
            "description": "Special languages, such as constructed languages (e.g., Esperanto, Klingon)"
        }
    }

    LANGUAGE_TYPE_DESCRIPTIONS = {
        "L": {
            "label": "Living",
            "description": "A language spoken by a community, currently in use (e.g., English, French)"
        },
        "E": {
            "label": "Extinct",
            "description": "A language that is no longer in use or spoken (e.g., Latin, Ancient Greek)"
        },
        "A": {
            "label": "Ancient",
            "description": "A language that was spoken in ancient times but is not used anymore (e.g., Sanskrit, Old English)"
        },
        "C": {
            "label": "Constructed",
            "description": "A language that was artificially created (e.g., Esperanto, Dothraki)"
        },
        "S": {
            "label": "Sign",
            "description": "A language used for sign communication (e.g., American Sign Language, British Sign Language)"
        },
        "P": {
            "label": "Pidgin",
            "description": "A simplified language formed from two or more languages, often for trade or communication (e.g., Hawaiian Pidgin)"
        },
        "C": {
            "label": "Creole",
            "description": "A stable, fully developed natural language that has evolved from a pidgin (e.g., Haitian Creole)"
        }
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# ISO 639-3 metadata\n")
        f.write("SCOPE_DESCRIPTIONS = ")
        f.write(json.dumps(SCOPE_DESCRIPTIONS, indent=4, ensure_ascii=False))
        f.write("\n\n")

        f.write("LANGUAGE_TYPE_DESCRIPTIONS = ")
        f.write(json.dumps(LANGUAGE_TYPE_DESCRIPTIONS, indent=4, ensure_ascii=False))
        f.write("\n\n")

        f.write("# ISO 639-3 to ISO 639-2 mapping\n")
        f.write("ISO_639_3 = ")
        f.write(json.dumps(iso_639_3, indent=4, ensure_ascii=False))
        f.write("\n\n")

        f.write("# ISO 639-1 to ISO 639-3 mapping\n")
        f.write("ISO_639_1_TO_3 = ")
        f.write(json.dumps(iso_639_1_to_3, indent=4, ensure_ascii=False))
        f.write("\n")


if __name__ == "__main__":
    try:
        iso_639_3, iso_639_1_to_3 = fetch_iso639()
        save_mapping(iso_639_3, iso_639_1_to_3)
        print(f"ISO 639 mapping saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error: {e}")
