# /ingestion/transformers.py "Robots in Disguise"
import json
import logging

from subtransformers.geonames.names import NamesProcessor as GeonamesNamesProcessor
from subtransformers.loc.links import LinksProcessor as LOCLinksProcessor
from subtransformers.osm.names import NamesProcessor as OSMNamesProcessor
from subtransformers.osm.types import TypesProcessor as OSMTypesProcessor
from subtransformers.pleiades.links import LinksProcessor as PleiadesLinksProcessor
from subtransformers.pleiades.locations import LocationsProcessor as PleiadesLocationsProcessor
from subtransformers.pleiades.names import NamesProcessor as PleiadesNamesProcessor
from subtransformers.pleiades.types import TypesProcessor as PleiadesTypesProcessor
from subtransformers.pleiades.years import YearsProcessor as PleiadesYearsProcessor
from subtransformers.tgn.linked_art import LinkedArtProcessor
from subtransformers.wikidata.locations import LocationsProcessor as WikidataLocationsProcessor
from subtransformers.wikidata.names import NamesProcessor as WikidataNamesProcessor
from subtransformers.wikidata.types import TypesProcessor as WikidataTypesProcessor
from ..gis.processor import GeometryProcessor
from ..gis.utils import geo_to_cartesian
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
                    "id": (document_id := get_uuid()),
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
                        "id": toponym_id,
                        "fields": {
                        }
                    }
                ],
                None  # Links # TODO
            )
        ],
        "ISO3166": [
            lambda data: (
                {
                    "id": (document_id := get_uuid()),
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
                        "id": toponym_id,
                        "fields": {
                            "name_strict": (name := data.get("properties", {}).get("ADMIN")),
                            "name": name,
                            "places": [document_id],
                            "bcp47_language": "en",
                        }
                    }
                ],
                None  # No links
            )
        ],
        "Pleiades": [
            # TODO: Before running this, augment the types dictionary
            lambda data: (
                {
                    "id": (document_id := get_uuid()),
                    "fields": {
                        **({"record_id": record_id} if (record_id := data.get("id")) else {}),
                        **({"record_url": f"https://pleiades.stoa.org/places/{record_id}"} if record_id else {}),
                        **({"names": names["names"]} if (
                            names := PleiadesNamesProcessor(document_id, data.get("names"),
                                                            data.get("title")).process()) else {}),
                        **(type_classes if (  # Map Pleiades place types to GeoNames feature classes and AAT types
                            type_classes := PleiadesTypesProcessor(data.get("placeTypeURIs")).process()) else {}),
                        **(geometry_etc if (
                            # Includes abstracted geometry properties, iso country codes, and array of locations
                            geometry_etc := PleiadesLocationsProcessor(data.get("locations")).process()) else {}),

                        **(years if (years := PleiadesYearsProcessor(data.get("names"),
                                                                     data.get("locations")).process()) else {}),
                    }
                },
                names["toponyms"] if names else None,
                PleiadesLinksProcessor(document_id, record_id, data.get("connections")).process()
            )
        ],
        "GeoNames": [
            # All geometries are points, so the following is much more efficient than using the GeometryProcessor
            lambda data: (  # Transform the primary record
                {
                    "id": (document_id := data.get("geonameid", get_uuid())),
                    "fields": {
                        **({"record_id": record_id} if (record_id := data.get("geonameid")) else {}),
                        **({"record_url": f"https://www.geonames.org/{record_id}"} if record_id else {}),
                        "names": [
                            {"toponym_id": (toponym_id := get_uuid()), "year_start": 2025, "year_end": 2025},
                        ],
                        **({"bbox_sw_lat": bbox_sw_lat} if (bbox_sw_lat := float(data.get("latitude"))) else {}),
                        **({"bbox_sw_lng": bbox_sw_lng} if (bbox_sw_lng := float(data.get("longitude"))) else {}),
                        **({"bbox_ne_lat": bbox_sw_lat} if bbox_sw_lat else {}),
                        **({"bbox_ne_lng": bbox_sw_lng} if bbox_sw_lng else {}),
                        "bbox_antimeridial": False,
                        **({"convex_hull": point} if (point := json.dumps({
                            "type": "Point",
                            "coordinates": [bbox_sw_lng, bbox_sw_lat]
                        }) if bbox_sw_lng and bbox_sw_lat else None) else {}),
                        **({"locations": [{"geometry": point}]} if point else {}),
                        **({"representative_point": {"lat": bbox_sw_lat,
                                                     "lng": bbox_sw_lng}} if bbox_sw_lat and bbox_sw_lng else {}),
                        **({"cartesian": geo_to_cartesian(bbox_sw_lat,
                                                          bbox_sw_lng)} if bbox_sw_lat and bbox_sw_lng else {}),
                        **({"classes": classes} if (classes := [data.get("feature_class", "")]) else {}),
                        **({"ccodes": [ccode]} if (ccode := data.get("country_code")) else {}),
                    }
                },
                [
                    {
                        "id": toponym_id,
                        "fields": {
                            "is_staging": True,
                            "name_strict": (name := data.get("name", "")),
                            "name": name,
                            "places": [document_id],
                            "bcp47_language": "en",
                        }
                    }
                ],
                None  # No links
            ),
            lambda data: (  # Transform the alternate names
                {
                    "id": get_uuid(),
                    "fields": {
                        "is_staging": True,
                        "record_id": (document_id := data.get("geonameid")),
                        **({"names": names["names"]} if (
                            names := GeonamesNamesProcessor(document_id, data).process()) else {}),
                    }
                },
                names["toponyms"] if names else None,
                names["links"] if names else None
            ),
        ],
        "TGN": [
            lambda data: (
                {
                    "id": linked_art["id"] if (
                        linked_art := LinkedArtProcessor(data).process()) else None,
                    "fields": linked_art["place"] if linked_art else {},
                },
                linked_art["toponyms"] if linked_art else None,
                linked_art["links"] if linked_art else None
            # TODO: Implement links for hierarchical relationships between places
            )
        ],
        "Wikidata": [  # Depends on GeoNames having been already processed
            lambda data: (
                {
                    "id": (document_id := data.get("id", get_uuid())),
                    "fields": {
                        "record_id": document_id,
                        "record_url": f"https://www.wikidata.org/wiki/Special:EntityData/{document_id}.json",
                        **({"names": names["names"]} if (
                            names := WikidataNamesProcessor(document_id, data.get("labels")).process()) else {}),
                        **(type_classes if (
                            # Map Wikidata place types to GeoNames feature classes and AAT types: TODO: Currently maps types to wd: QIDs
                            type_classes := WikidataTypesProcessor(data.get("claims", {}).get("P31", {}),
                                                                   data.get("claims", {}).get("P1566",
                                                                                              {})).process()) else {}),
                        **(geometry_etc if (
                            # Includes abstracted geometry properties, iso country codes, and array of locations
                            geometry_etc := WikidataLocationsProcessor(
                                data.get("claims", {}).get("P625", [])).process()) else {}),
                    }
                },
                names["toponyms"] if names else None,
                [  # No links
                ]
            )
        ],
        "OSM": [
            lambda data: (
                {  # Feature and Locations
                    "id": (document_id := get_uuid()),
                    "fields": {
                        **({"names": names["names"]} if (
                            names := OSMNamesProcessor(document_id,
                                                       (properties := data.get("properties"))).process()) else {}),
                        **(geometry_etc if (  # Includes abstracted geometry properties and array of locations
                            geometry_etc := GeometryProcessor(data.get("geometry")).process()) else {}),
                        **(type_classes if (  # Map OSM place type to GeoNames feature classes and AAT types
                            type_classes := OSMTypesProcessor(
                                next(
                                    (properties[key] for key in ['geological', 'historic', 'place', 'water', 'waterway']
                                     if key in properties and properties[key]),
                                    None
                                )
                            ).process()) else {}),
                    }
                },
                names["toponyms"] if names else None,
                [  # Links
                    {
                        "place_id": document_id,
                        "predicate": "owl:sameAs",
                        "object": f"wd:{wikidata}",
                    }
                ] if (wikidata := properties.get("wikidata")) else []
            )
        ],
        "LOC": [
            lambda data: (
                {
                },
                [
                ],
                LOCLinksProcessor(data.get("@graph")).process()
            )
        ],
        "GB1900": [
            # All geometries are points
            lambda data: (
                {
                    "id": (document_id := data.get("pin_id", get_uuid())),
                    "fields": {
                        "record_id": document_id,
                        "names": [
                            {"toponym_id": (toponym_id := get_uuid()), "year_start": 1888, "year_end": 1914},
                        ],
                        **({"bbox_sw_lat": bbox_sw_lat} if (bbox_sw_lat := float(data.get("latitude"))) else {}),
                        **({"bbox_sw_lng": bbox_sw_lng} if (bbox_sw_lng := float(data.get("longitude"))) else {}),
                        **({"bbox_ne_lat": bbox_sw_lat} if bbox_sw_lat else {}),
                        **({"bbox_ne_lng": bbox_sw_lng} if bbox_sw_lng else {}),
                        "bbox_antimeridial": False,
                        **({"convex_hull": point} if (point := json.dumps({
                            "type": "Point",
                            "coordinates": [bbox_sw_lng, bbox_sw_lat]
                        }) if bbox_sw_lng and bbox_sw_lat else None) else {}),
                        **({"locations": [{"geometry": point}]} if point else {}),
                        **({"representative_point": {"lat": bbox_sw_lat,
                                                     "lng": bbox_sw_lng}} if bbox_sw_lat and bbox_sw_lng else {}),
                        **({"cartesian": geo_to_cartesian(bbox_sw_lat,
                                                          bbox_sw_lng)} if bbox_sw_lat and bbox_sw_lng else {}),
                        "ccodes": ["GB"],
                    }
                },
                [
                    {
                        "id": toponym_id,
                        "fields": {
                            "is_staging": True,
                            "name_strict": (name := data.get("final_text", "")),
                            "name": name,
                            "places": [document_id],
                            "bcp47_language": "en",
                        }
                    }
                ],
                None  # No links
            )
        ],
        "Terrarium": [  # GeoJSON detailing sources of DEM data
            lambda data: (
                {
                    "id": get_uuid(),
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
                [  # No names
                ],
                [  # No links
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
