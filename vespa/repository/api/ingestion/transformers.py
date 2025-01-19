# /ingestion/transformers.py "Robots in Disguise"
import json
import logging

from .subtransformers.pleiades.links import LinksProcessor as PleiadesLinksProcessor
from .subtransformers.pleiades.locations import LocationsProcessor as PleiadesLocationsProcessor
from .subtransformers.pleiades.names import NamesProcessor as PleiadesNamesProcessor
from .subtransformers.pleiades.types import TypesProcessor as PleiadesTypesProcessor
from .subtransformers.pleiades.years import YearsProcessor as PleiadesYearsProcessor
from ..gis.intersections import GeometryIntersect
from ..gis.processor import GeometryProcessor
from ..utils import get_uuid

logger = logging.getLogger(__name__)


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
        "LPF": [  # Linked Places Format: default transformer for extended GeoJSON Feature
            lambda data: (
                {  # Feature and Locations
                    "document_id": (document_id := get_uuid()),
                    "fields": {
                        "names": [
                            # TODO: Code a general ToponymProcessor to produce names and attestations
                            {"toponym_id": (toponym_id := get_uuid()), "year_start": 2018, "year_end": 2018,
                             "is_preferred": 1},
                        ],
                        **(geometry_etc if (  # Includes abstracted geometry properties and array of locations
                            geometry_etc := GeometryProcessor(data.get("geometry")).process()) else {}),
                        "lpf_feature": json.dumps(data),
                    }
                },
                [  # Attestations and Toponyms # TODO
                    {
                        "document_id": toponym_id,
                        "fields": {
                        }
                    }
                ],
                None # Links # TODO
            )
        ],
        "ISO3166": [
            lambda data: (
                {
                    "document_id": (document_id := get_uuid()),
                    "fields": {
                        "names": [
                            {"toponym_id": (toponym_id := get_uuid()), "year_start": 2018, "year_end": 2018,
                             "is_preferred": 1},
                        ],
                        "meta": json.dumps({
                            "ISO_A2": data.get("properties", {}).get("ISO_A2"),
                        }),
                        **(geometry_etc if (
                            geometry_etc := GeometryProcessor(data.get("geometry"),
                                                              values=["bbox", "geometry"]).process()) else {}),
                        "year_start": 2018,
                        # Boundaries last updated: see https://github.com/datasets/geo-countries/tree/main/data
                        "year_end": 2018,
                        "ccodes": data.get("code2"),
                        "classes": ["A"],
                        "types": ["300232420"],  # https://vocab.getty.edu/aat/300232420 'sovereign states'
                    }
                },
                [
                    {
                        "document_id": toponym_id,
                        "fields": {
                            "name": data.get("properties", {}).get("ADMIN"),
                            "places": [document_id],
                            "bcp47_language": "en",
                        }
                    }
                ],
                None # No links
            )
        ],
        "Pleiades": [
            lambda data: (
                {
                    "document_id": (document_id := get_uuid()),
                    "fields": {
                        **({"record_id": record_id} if (record_id := data.get("id")) else {}),
                        **({"record_url": f"https://pleiades.stoa.org/places/{record_id}"} if record_id else {}),
                        **({"names": names["names"]} if (
                            names := PleiadesNamesProcessor(document_id, data.get("names"), data.get("title")).process()) else {}),
                        **(type_classes if (  # Map Pleiades place types to GeoNames feature classes and AAT types
                            type_classes := PleiadesTypesProcessor(data.get("placeTypeURIs")).process()) else {}),
                        **(geometry_etc if (  # Includes abstracted geometry properties, iso country codes, and array of locations
                            geometry_etc := PleiadesLocationsProcessor(data.get("locations")).process()) else {}),

                        **(years if (years := PleiadesYearsProcessor(data.get("names"), data.get("locations")).process()) else {}),
                    }
                },
                names["toponyms"] if names else None,
                PleiadesLinksProcessor(document_id, record_id, data.get("connections")).process()
            )
        ],
        "GeoNames": [  # TODO
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
                            GeometryIntersect(geometry={"type": "Point", "coordinates": [float(data["latitude"]), float(
                                data["longitude"])]}).resolve()
                            if data.get("latitude") and data.get("longitude") else None
                        )
                    ),
                    "lpf_feature": {},
                },
                None,
                None  # No links
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
                else None,
                None # No links
            )
        ],
        "TGN": [  # TODO
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
            [ # No links
            ]
        ],
        "Wikidata": [  # TODO
            lambda data: (
                {
                },
                [
                ],
                [ # No links
                ]
            )
        ],
        "OSM": [  # TODO
            lambda data: (
                {
                },
                [
                ],
                [ # No links
                ]
            )
        ],
        "LOC": [  # TODO
            lambda data: (
                {
                },
                [
                ],
                [ # No links
                ]
            )
        ],
        "GB1900": [  # TODO
            lambda data: (
                {
                },
                [
                ],
                [ # No links
                ]
            )
        ],
        "Terrarium": [  # GeoJSON detailing sources of DEM data
            lambda data: (
                {
                    "document_id": get_uuid(),
                    "fields": {
                        **({"geometry": geometry_etc.get("locations")[0].get("geometry")} if (
                            geometry_etc := GeometryProcessor(data.get("geometry"),
                                                              values=["bbox", "geometry"]).process()) else {}),
                        **({"bbox_sw_lat": geometry_etc.get("bbox_sw_lat")} if geometry_etc else {}),
                        **({"bbox_sw_lng": geometry_etc.get("bbox_sw_lng")} if geometry_etc else {}),
                        **({"bbox_ne_lat": geometry_etc.get("bbox_ne_lat")} if geometry_etc else {}),
                        **({"bbox_ne_lng": geometry_etc.get("bbox_ne_lng")} if geometry_etc else {}),
                        **({"resolution": float(resolution)} if (resolution := data.get("properties", {}).get(
                            "resolution")) is not None else {}),
                        **({"source": source} if (source := data.get("properties", {}).get("source")) else {}),
                    }
                },
                [ # No names
                ],
                [ # No links
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
        # logger.info(f"Transformed data: {results}")
        return results
