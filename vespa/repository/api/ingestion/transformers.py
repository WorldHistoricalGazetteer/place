# /ingestion/transformers.py
from ..gis.utils import isocodes, bbox, float_geometry
from ..utils import get_uuid


class DocTransformer:
    """
    A utility class for transforming raw data from various geographic or historical datasets
    into a consistent format, primarily the Normalised Place Record (NPR) format.

    The transformation process involves:
    - Structuring raw data into a standardised NPR schema.
    - Extracting and linking toponyms and attestations associated with the data.

    Supported datamodels:
        - "LPF" (Linked Places Format): Default transformer for generic data.
        - "Pleiades": Converts Pleiades dataset into NPR and extracts toponyms.
        - "GeoNames": Handles GeoNames primary and alternate names.
        - "TGN" (Getty Thesaurus of Geographic Names): Processes hierarchical and geospatial data.
        - "Wikidata": (Placeholder).
        - "OSM" (OpenStreetMap): (Placeholder).
        - "LOC" (Library of Congress): (Placeholder).
        - "GB1900": (Placeholder).

    Attributes:
        transformers (dict): A mapping of dataset names to lists of transformation functions.
            Each function is a lambda that takes raw data as input and returns:
            - A dictionary representing the NPR structure.
            - A list of associated toponyms and attestations, if applicable.

    Methods:
        transform(data, dataset_name):
            Transforms raw data from a specified dataset into NPR format.
            Raises a ValueError if the dataset is not supported.

    Example Usage:
        >>> data = {
                "id": "123",
                "title": "Athens",
                "reprPoint": [37.9838, 23.7275],
                "bbox": [37.9, 23.7, 38.0, 23.8],
                "placeTypes": ["city"],
                "names": [
                    {"attested": "Athinai", "language": "el", "start": -500, "end": 1453},
                    {"romanized": "Athens", "language": "en", "start": 1453}
                ]
            }
        >>> result = DocTransformer.transform(data, "Pleiades")
        >>> print(result)

    Notes:
        - This class can be extended with additional datamodel-specific transformers.
        - For unsupported datasets, placeholder transformers can be updated to implement
          custom transformation logic.
    """

    transformers = {
        "LPF": [  # Linked Places Format: default transformer
            lambda data: (
                {  # NPR (Normalised Place Record)
                    # "item_id": ,
                    # "primary_name": ,
                    # "latitude": ,
                    # "longitude": ,
                    # "geometry_bbox": ,
                    # "feature_classes": ,
                    # "ccodes": ,
                    "lpf_feature": data,
                },
                [  # Attestations and Toponyms
                ]
            )
        ],
        "Pleiades": [
            lambda data: (
                {
                    "item_id": data.get("id", ""),
                    "primary_name": data.get("title", ""),
                    "latitude": float(data["reprPoint"][0]) if isinstance(data.get("reprPoint"), list) and len(
                        data["reprPoint"]) == 2 else None,
                    "longitude": float(data["reprPoint"][1]) if isinstance(data.get("reprPoint"), list) and len(
                        data["reprPoint"]) == 2 else None,
                    "geometry_bbox": (
                        [float(coord) for coord in data["bbox"]]
                        if isinstance(data.get("bbox"), list) and len(data["bbox"]) == 4
                        else None
                    ),
                    # TODO: Map to GeoNames feature classes from https://pleiades.stoa.org/vocabularies/place-types
                    "feature_classes": data.get("placeTypes", []),
                    "ccodes": isocodes(
                        data.get("features", [{'type': 'Point', 'coordinates': data.get("reprPoint", None)}]),
                        has_decimal=True),
                    "lpf_feature": {},  # TODO: Build LPF feature
                },
                [
                    {
                        "toponym": data.get("title", ""),  # Add root title as toponym
                        "language": "",  # Language unknown for root title
                        "is_romanised": False,  # Assume title is not romanised
                        # TODO: No time data for root toponym, but could be inferred from other attributes?
                    }
                ] + [
                    {
                        "toponym": name.get("attested") or name.get("romanized", ""),
                        "language": name.get("language", ""),  # TODO: Use BCP 47 language tags
                        "is_romanised": not name.get("attested"),
                        "start": name.get("start", None),
                        "end": name.get("end", None),
                    }
                    for name in data.get("names", [])
                ]
            )
        ],
        "GeoNames": [
            lambda data: (  # Transform the primary record
                {
                    "item_id": data.get("geonameid", ""),
                    "primary_name": data.get("name", ""),
                    "latitude": float(data.get("latitude")) if data.get("latitude") else None,
                    "longitude": float(data.get("longitude")) if data.get("longitude") else None,
                    "geometry_bbox": None,
                    "feature_classes": [data.get("feature_class", "")],
                    "ccodes": (
                        data.get("cc2", "").split(",")
                        if data.get("cc2") else
                        [data.get("country_code")] or (
                            isocodes(
                                [{'type': 'Point', 'coordinates': [float(data["latitude"]), float(data["longitude"])]}]
                            ) if data.get("latitude") and data.get("longitude") else None
                        )
                    ),
                    "lpf_feature": {},
                },
                None
            ),
            lambda data: (  # Transform the alternate names
                {
                    "item_id": data.get("geonameid", ""),
                },
                [
                    {
                        "npr_item_id": data.get("geonameid", ""),
                        "source_toponym_id": data.get("alternateNameId", ""),
                        "toponym": data.get("alternate_name", ""),
                        "language": data.get("isolanguage") or None,
                        "is_preferred": bool(data.get("isPreferredName", False)),
                        "start": data.get("from") or None,
                        "end": data.get("to") or None,
                    }
                ]
                if data.get("isolanguage") not in ["post", "iata", "icao", "faac", "abbr", "link",
                                                   "wkdt"]  # Skip non-language codes
                else None
            )
        ],
        "TGN": [
            lambda data: (
                {  # Subjects
                    "item_id": int(data.get("subject", "").split('/')[-1]),
                    "primary_name": data.get("object", "").strip('"').encode('utf-8').decode('unicode_escape'),
                } if data.get("predicate") == "http://vocab.getty.edu/ontology#parentString" else

                # TODO: Map to GeoNames feature classes from aat:
                {  # PlaceTypes
                    "item_id": int(data.get("subject", "").split('/')[-1]),
                    "feature_classes": [data.get("object", "").split('/')[-1]],
                } if data.get("predicate") == "http://vocab.getty.edu/ontology#placeType" else

                {  # Coordinates
                    "item_id": int(data.get("subject", "").split('/')[-1].split('-')[0]),
                    **({"longitude": float(data.get("object", "").split("^^")[0].strip('"'))} if data.get("predicate",
                                                                                                          "") == "http://schema.org/longitude" else {}),
                    **({"latitude": float(data.get("object", "").split("^^")[0].strip('"'))} if data.get("predicate",
                                                                                                         "") == "http://schema.org/latitude" else {}),
                } if data.get("predicate") in ["http://schema.org/longitude", "http://schema.org/latitude"] else

                # Terms
                {"item_id": data.get("subject", "").split('/')[-1]} if data.get("predicate") in [
                    "http://vocab.getty.edu/ontology#prefLabelGVP",
                    "http://www.w3.org/2008/05/skos-xl#prefLabel",
                    "http://www.w3.org/2008/05/skos-xl#altLabel"] else

                None,
                [
                    {  # Terms
                        **({"npr_item_id": data.get("subject", "").split('/')[-1]} if data.get("predicate") in [
                            "http://vocab.getty.edu/ontology#prefLabelGVP",
                            "http://www.w3.org/2008/05/skos-xl#prefLabel",
                            "http://www.w3.org/2008/05/skos-xl#altLabel"] else {}
                           ),
                        "source_toponym_id": data.get("subject", "").split('/')[-1] if data.get("predicate") in [
                            "http://vocab.getty.edu/ontology#term",
                            "http://vocab.getty.edu/ontology#estStart"] else
                        data.get("object", "").split('/')[-1],
                        **({"toponym": data.get("object", "").encode('utf-8').decode('unicode_escape').split("@")[
                            0].strip('"')} if data.get(
                            "predicate") == "http://vocab.getty.edu/ontology#term" else {}),
                        **({"language": data.get("object", "").encode('utf-8').decode('unicode_escape').split("@")[
                            -1]} if len(
                            data.get("object", "").split("@")) == 2 and data.get(
                            "predicate") == "http://vocab.getty.edu/ontology#term" else {}),
                        **({"is_preferred": True} if data.get(
                            "predicate") == "http://vocab.getty.edu/ontology#prefLabelGVP" else {}),
                        **({"start": int(data.get("object", "").split("^^")[0].strip('"'))} if data.get(
                            "predicate") == "http://vocab.getty.edu/ontology#estStart" else {}),
                    }
                ] if data.get("predicate") in ["http://vocab.getty.edu/ontology#prefLabelGVP",
                                               "http://www.w3.org/2008/05/skos-xl#prefLabel",
                                               "http://www.w3.org/2008/05/skos-xl#altLabel",
                                               "http://vocab.getty.edu/ontology#term",
                                               "http://vocab.getty.edu/ontology#estStart"] else

                None
            ),
        ],
        "Wikidata": [
            lambda data: (
                {
                },
                [
                ]
            )
        ],
        "OSM": [
            lambda data: (
                {
                },
                [
                ]
            )
        ],
        "LOC": [
            lambda data: (
                {
                },
                [
                ]
            )
        ],
        "GB1900": [
            lambda data: (
                {
                },
                [
                ]
            )
        ],
        "ISO3166": [
            lambda data: (
                {
                    "put": f"id:vespa:iso3166::{data.get('properties', {}).get('ISO_A2', get_uuid())}",
                    "fields": {
                        "name": data.get("properties", {}).get("ADMIN", None),
                        "code2": data.get("properties", {}).get("ISO_A2", None),
                        "code3": data.get("properties", {}).get("ISO_A3", None),
                        "geometry": data.get("geometry", None),
                        "bounding_box": bbox(data.get("geometry"), errors=False) or {"x": [None, None], "y": [None, None]},
                    },
                },
                [
                ]
            )
        ],
        "Terrarium": [
            lambda data: (
                {
                    "put": f"id:vespa:terrarium::{data.get('properties', {}).get('id', get_uuid())}",
                    "fields": {
                        "resolution": data.get("properties", {}).get("resolution", None),
                        "source": data.get("properties", {}).get("source", None),
                        "geometry": float_geometry(data.get("geometry", None), True),
                        "bounding_box": bbox(data.get("geometry"), errors=False) or {"x": [None, None], "y": [None, None]},
                    },
                },
                [
                ]
            )
        ],
    }

    @staticmethod
    def transform(data, dataset_name, transformer_index=0):
        transformer = DocTransformer.transformers.get(dataset_name)[transformer_index]
        if not transformer:
            raise ValueError(f"Unknown dataset name: {dataset_name}")

        results = transformer(data)
        return results
