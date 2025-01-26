# /ingestion/config.py

NATIVE_LAND_API_KEY = ''  # Use Native Land API Key from https://native-land.ca/dashboard

# Remote Dataset Configurations
REMOTE_DATASET_CONFIGS = [
    {  # 2024: 37k+ places
        'dataset_name': 'Pleiades',
        'namespace': 'pleiades',
        'vespa_schema': 'place',
        'api_item': 'https://pleiades.stoa.org/places/<id>/json',
        'citation': 'Pleiades: A community-built gazetteer and graph of ancient places. Copyright © Institute for the Study of the Ancient World. Sharing and remixing permitted under terms of the Creative Commons Attribution 3.0 License (cc-by). https://pleiades.stoa.org/',
        'files': [
            {
                'url': 'https://atlantides.org/downloads/pleiades/json/pleiades-places-latest.json.gz',  # 104MB
                'file_type': 'json',
                'item_path': '@graph',
            }
        ],
    },
    {  # 2024: 12m+ places
        'dataset_name': 'GeoNames',
        'namespace': 'gn',
        'vespa_schema': 'place',
        'api_item': 'http://api.geonames.org/getJSON?formatted=true&geonameId=<id>&username=<username>&style=full',
        'citation': 'GeoNames geographical database. https://www.geonames.org/',
        'files': [
            {
                'url': 'https://download.geonames.org/export/dump/allCountries.zip',  # 405MB
                'fieldnames': [
                    'geonameid', 'name', 'asciiname', 'alternatenames', 'latitude', 'longitude', 'feature_class',
                    'feature_code', 'country_code', 'cc2', 'admin1_code', 'admin2_code', 'admin3_code', 'admin4_code',
                    'population', 'elevation', 'dem', 'timezone', 'modification_date',
                ],
                'file_name': 'allCountries.txt',
                'file_type': 'csv',
                'delimiter': '\t',
            },
            {
                'url': 'https://download.geonames.org/export/dump/alternateNamesV2.zip',  # 193MB
                'update_place': True,  # Update existing place with alternate names
                'fieldnames': [
                    'alternateNameId', 'geonameid', 'isolanguage', 'alternate_name', 'isPreferredName',
                    'isShortName', 'isColloquial', 'isHistoric', 'from', 'to',
                ],
                'file_name': 'alternateNamesV2.txt',  # Zip file also includes iso-languagecodes.txt
                'file_type': 'csv',
                'delimiter': '\t',
                'filters': [
                    lambda row: row.get('isolanguage') not in ['post', 'link', 'iata', 'icao', 'faac', 'tcid', 'unlc',
                                                               'abbr'],
                ]
            },
        ],
    },
    {  # 2024: 3m+ places
        'dataset_name': 'TGN',
        'namespace': 'tgn',
        'vespa_schema': 'npr',
        'api_item': 'https://vocab.getty.edu/tgn/<id>.jsonld',
        'citation': 'The Getty Thesaurus of Geographic Names® (TGN) is provided by the J. Paul Getty Trust under the Open Data Commons Attribution License (ODC-By) 1.0. https://www.getty.edu/research/tools/vocabularies/tgn/',
        'files': [
            {
                'url': 'http://tgndownloads.getty.edu/VocabData/full.zip',
                'local_name': 'tgn_full.zip',  # 1.98GB
                'file_name': 'TGNOut_Full.nt',
                'file_type': 'nt',
                'filters': [  # Filter to only include records with these predicates
                    # lambda triple: triple['predicate'] == '<http://vocab.getty.edu/ontology#parentString>', # <http://vocab.getty.edu/tgn/7011179> <http://vocab.getty.edu/ontology#parentString> "Siena, Tuscany, Italy, Europe, World"
                    lambda triple: triple.get('predicate') == 'http://vocab.getty.edu/ontology#prefLabelGVP',
                    # '<http://vocab.getty.edu/tgn/7011179> <http://vocab.getty.edu/ontology#prefLabelGVP> <http://vocab.getty.edu/tgn/term/47413-en>
                    lambda triple: triple.get('predicate') == 'http://www.w3.org/2008/05/skos-xl#prefLabel',
                    # <http://vocab.getty.edu/tgn/7011179> <http://www.w3.org/2008/05/skos-xl#prefLabel> <http://vocab.getty.edu/tgn/term/47413-en>
                    lambda triple: triple.get('predicate') == 'http://www.w3.org/2008/05/skos-xl#altLabel',
                    # <http://vocab.getty.edu/tgn/7011179> <http://www.w3.org/2008/05/skos-xl#altLabel> <http://vocab.getty.edu/tgn/term/140808-en>
                    lambda triple: triple.get('predicate') == 'http://vocab.getty.edu/ontology#term',
                    # <http://vocab.getty.edu/tgn/term/47413-en> <http://vocab.getty.edu/ontology#term> "Siena"@en
                    lambda triple: triple.get('predicate') == 'http://vocab.getty.edu/ontology#estStart',
                    # <http://vocab.getty.edu/tgn/term/47413-en> <http://vocab.getty.edu/ontology#estStart> "1200"^^<http://www.w3.org/2001/XMLSchema#gYear>
                    lambda triple: triple.get('predicate') == 'http://vocab.getty.edu/ontology#estEnd',
                    # <http://vocab.getty.edu/tgn/term/47413-en> <http://vocab.getty.edu/ontology#estEnd> "1200"^^<http://www.w3.org/2001/XMLSchema#gYear>
                    lambda triple: triple.get('predicate') == 'http://schema.org/longitude',
                    # <http://vocab.getty.edu/tgn/7011179-geometry> <http://schema.org/longitude> "11.33"^^<http://www.w3.org/2001/XMLSchema#decimal>
                    lambda triple: triple.get('predicate') == 'http://schema.org/latitude',
                    # <http://vocab.getty.edu/tgn/7011179-geometry> <http://schema.org/latitude> "43.318"^^<http://www.w3.org/2001/XMLSchema#decimal>
                    lambda triple: triple.get('predicate') == 'http://vocab.getty.edu/ontology#placeType',
                    # <http://vocab.getty.edu/tgn/7011179> <http://vocab.getty.edu/ontology#placeType> <http://vocab.getty.edu/aat/300387236>
                ],
            },
        ],
    },
    {  # 2024: 8m+ items classified as places
        'dataset_name': 'Wikidata',
        'namespace': 'wd',
        'vespa_schema': 'npr',
        'api_item': 'https://www.wikidata.org/wiki/Special:EntityData/<id>.json',
        'citation': 'Wikidata is a free and open knowledge base that can be read and edited by both humans and machines. https://www.wikidata.org/',
        'files': [
            {
                'url': 'https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz',  # 133GB
                'local_name': '/data/k8s/vespa-ingestion/wikidata.json.gz',  # 133GB
                'file_type': 'json',
                'item_path': 'entities',
                'filters': [
                    lambda doc: 'claims' in doc and 'P625' in doc['claims'],
                    # Filter to only include items with coordinates
                ]
            },
        ],
    },
    {  # 2024: <22m named places with multiple toponyms (file includes some unnamed features)
        'dataset_name': 'OSM',
        'namespace': 'osm',
        'vespa_schema': 'npr',
        'api_item': 'https://nominatim.openstreetmap.org/details.php?osmtype=R&osmid=<id>&format=json',
        'citation': 'OpenStreetMap is open data, licensed under the Open Data Commons Open Database License (ODbL). https://www.openstreetmap.org/',
        'files': [
            {
                'url': 'https://planet.openstreetmap.org/pbf/planet-latest.osm.pbf',  # 84.7GB
                'local_name': 'osm.geojsonseq',  # 4.1GB
                'file_type': 'geojsonseq',
                'filters': [
                    lambda feature: 'name' in (properties := feature['properties']) and
                                    any(key in properties for key in
                                        ['geological', 'historic', 'place', 'water', 'waterway']),
                    # Filter to only include named features
                ]
            }
        ],
    },
    {
        'dataset_name': 'LOC',
        'namespace': 'loc',
        'vespa_schema': 'npr',
        'api_item': 'https://www.loc.gov/item/<id>/',
        'citation': 'Library of Congress. https://www.loc.gov/',
        'files': [
            {
                'url': 'http://id.loc.gov/download/authorities/names.madsrdf.jsonld.gz',
                'file_type': 'json',
            }
        ],
    },
    {
        'dataset_name': 'NativeLand',
        'namespace': 'nl',
        'vespa_schema': 'npr',
        'api_item': '',
        'citation': 'Native Land Digital. https://native-land.ca/',
        'files': [
            {
                'url': f'https://native-land.ca/api/polygons/geojson/territories?key={NATIVE_LAND_API_KEY}',
                'file_type': 'json',
                'item_path': 'features',
            },
            {
                'url': f'https://native-land.ca/api/polygons/geojson/languages?key={NATIVE_LAND_API_KEY}',
                'file_type': 'json',
                'item_path': 'features',
            },
            {
                'url': f'https://native-land.ca/api/polygons/geojson/treaties?key={NATIVE_LAND_API_KEY}',
                'file_type': 'json',
                'item_path': 'features',
            }
        ],
    },
    {
        'dataset_name': 'DPlace',
        'namespace': 'dplace',
        'vespa_schema': 'npr',
        'api_item': '',
        'citation': 'D-PLACE: A Global Database of Cultural, Linguistic and Environmental Diversity. https://d-place.org/',
        'files': [
            {
                'url': f'https://d-place.org/languages.geojson',
                'file_type': 'json',
                'item_path': 'features',
            },
        ],
    },
    {
        'dataset_name': 'GB1900',
        'namespace': 'GB1900',
        'vespa_schema': 'npr',
        'api_item': '',
        'citation': 'GB1900 Gazetteer: British place names, 1888-1914. https://www.pastplace.org/data/#tabgb1900',
        'files': [
            {
                'url': 'https://www.pastplace.org/downloads/GB1900_gazetteer_abridged_july_2018.zip',
                'file_type': 'csv',
                'delimiter': ',',
            }
        ],
    },
    {  # 24,000 place names
        'dataset_name': 'IndexVillaris',
        'namespace': 'IV1680',
        'vespa_schema': 'npr',
        'api_item': '',
        'citation': 'Index Villaris, 1680',
        'files': [
            {
                'url': 'https://github.com/docuracy/IndexVillaris1680/raw/refs/heads/main/docs/data/IV-GB1900-OSM-WD.lp.json',
                'file_type': 'json',
            }
        ],
    },
    {  # ISO Countries
        'dataset_name': 'ISO3166',
        'namespace': 'iso3166',
        'vespa_schema': 'place',
        'api_item': '',
        'citation': 'Natural Earth Data. Public domain. https://www.naturalearthdata.com/',
        'files': [
            {
                'url': 'https://datahub.io/core/geo-countries/_r/-/data/countries.geojson',
                'file_type': 'json',
                'item_path': 'features',
            }
        ],
    },
    {  # Terrarium Sources
        'dataset_name': 'Terrarium',
        'namespace': 'terrarium',
        'vespa_schema': 'terrarium',
        'api_item': '',
        'citation': 'Mapzen Terrarium. https://github.com/mapzen/terrarium',
        'files': [
            {
                'url': 'https://s3.amazonaws.com/elevation-tiles-prod/docs/footprints.geojson.gz',
                'file_type': 'json',
                'item_path': 'features',
            }
        ],
    },
]
