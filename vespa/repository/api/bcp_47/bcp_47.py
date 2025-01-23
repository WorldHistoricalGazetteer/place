
"""
field bcp47_language type string {
    # Language (required): ISO 639-1/639-3 codes, e.g., "en", "zh".
    indexing: attribute | summary
    match { exact }
}

field bcp47_script type string {
    # Script (optional): ISO 15924 codes, e.g., "Latn", "Cyrl".
    indexing: attribute | summary
    match { exact }
}

field bcp47_region type string {
    # Region (optional): ISO 3166-1 alpha-2 codes, e.g., "GB", "US".
    indexing: attribute | summary
    match { exact }
}

field bcp47_variant type string {
    # Variant (optional): Custom identifiers, e.g., "pinyin", "pre1993".
    indexing: attribute | summary
    match { exact }
}
"""

bcp47_fields = ["language", "script", "region", "variant"]

def parse_bcp47_fields(bcp47: str) -> dict:
    """
    Parse a BCP 47 language tag into its constituent parts.

    Args:
        bcp47 (str): A BCP 47 language tag.

    Returns:
        dict: A dictionary of BCP 47 language tag parts.
    """
    parts = bcp47.split("-")
    return {
        f'bcp47_{field}': parts[i]
        for i, field in enumerate(bcp47_fields)
        if i < len(parts) and parts[i]
    }