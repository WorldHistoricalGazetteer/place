import requests
import re
import json

# The URL of the raw README file from the Epitran repository
GITHUB_README_URL = "https://raw.githubusercontent.com/dmort27/epitran/master/README.md"

# Output file for the dictionary
OUTPUT_FILE = "epitran_languages.py"

def fetch_readme(url):
    """Fetches the README content from the provided URL."""
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def parse_language_script_pairs(readme_text):
    """Parses the README content to extract the language/script pairs from the table."""
    # Split the README content by lines
    lines = readme_text.splitlines()

    # Flag to start parsing after the table header is found
    parsing = False
    langs = {}

    # Iterate over lines to find the table and extract pairs
    for line in lines:
        # Locate the header line containing "Code" and "Language (Script)"
        if "| Code        | Language (Script)       |" in line:
            parsing = True
            print("Parsing language/script pairs...")
            continue  # Skip the header line

        # If we are parsing and encounter a blank line, stop
        if parsing and not line.strip():
            break

        # If we are parsing, match the rows in the table
        if parsing:
            print(line)
            # Match lines that contain the language/script pairs (ignoring markdown formatting)
            match = re.match(r"\|\s+([A-Za-z0-9\-]+)\s*\|\s*(.+?)\s*\|", line.strip())
            if match:
                code = match.group(1).strip()
                language_script = match.group(2).strip()
                language_script = re.sub(r"[\\\*\†\‡].*", "", language_script).strip()
                langs[code] = language_script

    return langs

def save_mapping(mapping):
    """Saves the mapping as a Python dictionary in a file."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Epitran Language/Script Mapping\n")
        f.write("EPITRAN_LANGS = ")
        f.write(json.dumps(mapping, indent=4, ensure_ascii=False))
        f.write("\n")

if __name__ == "__main__":
    try:
        readme_text = fetch_readme(GITHUB_README_URL)
        lang_script_mapping = parse_language_script_pairs(readme_text)
        save_mapping(lang_script_mapping)
        print(f"Epitran language/script mapping saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error: {e}")
