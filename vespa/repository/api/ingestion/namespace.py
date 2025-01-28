namespaces = {
    "agrovoc": {
        "url": lambda curie: f"http://aims.fao.org/aos/agrovoc/{curie.split(':')[-1]}",
        "match": "/aims.fao.org/aos/agrovoc/",
    },
    "ark": {
        "url": lambda curie: f"http://n2t.net/ark:/{curie.split(':', 1)[-1]}",
        "match": "/n2t.net/ark:/",
    },
    "bbc": {
        "url": lambda curie: f"http://www.bbc.co.uk/things/{curie.split(':')[-1]}",
        "match": "/www.bbc.co.uk/things/",
    },
    "bne": {
        "url": lambda curie: f"http://datos.bne.es/resource/{curie.split(':')[-1]}",
        "match": "/datos.bne.es/resource/",
    },
    "bnf": {
        "url": lambda curie: f"http://catalogue.bnf.fr/ark:/12148/{curie.split(':')[-1]}",
        "match": ".bnf.fr/ark:/12148/",
    },
    "cabi": {
        "url": lambda curie: f"http://id.cabi.org/cabt/{curie.split(':')[-1]}",
        "match": "/id.cabi.org/cabt/",
    },
    "cantic": {
        "url": lambda curie: f"http://cantic.bnc.cat/registres/CUCId/{curie.split(':')[-1]}",
        "match": "cantic.bnc.cat/registres/CUCId/",
    },
    "dbp": {
        "url": lambda curie: f"http://dbpedia.org/resource/{curie.split(':')[-1]}",
        "match": "/dbpedia.org/",
    },
    "eionet": {
        "url": lambda curie: f"http://eionet.europa.eu/gemet/{curie.split(':')[-1]}",
        "match": "eionet.europa.eu/gemet/",
    },
    "emlo": {
        "url": lambda curie: f"http://emlo.bodleian.ox.ac.uk/profile/location/{curie.split(':')[-1]}",
        "match": "/emlo.bodleian.ox.ac.uk/profile/location/",
    },
    "eurovoc": {
        "url": lambda curie: f"http://eurovoc.europa.eu/{curie.split(':')[-1]}",
        "match": "/eurovoc.europa.eu/",
    },
    "fast": {
        "url": lambda curie: f"http://id.worldcat.org/fast/{curie.split(':')[-1]}",
        "match": "/id.worldcat.org/fast/",
    },
    "gesis": {
        "url": lambda curie: f"http://lod.gesis.org/thesoz/{curie.split(':')[-1]}",
        "match": "/lod.gesis.org/thesoz/",
    },
    "gemet": {
        "url": lambda curie: f"http://eionet.europa.eu/gemet/{curie.split(':')[-1]}",
        "match": "eionet.europa.eu/gemet/",
    },
    "gnd": {
        "url": lambda curie: f"http://d-nb.info/gnd/{curie.split(':')[-1]}",
        "match": "/d-nb.info/gnd/",
    },
    "gn": {
        "url": lambda curie: f"http://geonames.org/{curie.split(':')[-1]}",
        "match": "geonames.org/",
    },
    "ilo": {
        "url": lambda curie: f"http://metadata.ilo.org/thesaurus/{curie.split(':')[-1]}",
        "match": "/metadata.ilo.org/thesaurus/",
    },
    "imperium": {
        "url": lambda curie: f"http://imperium.ahlfeldt.se/places/{curie.split(':')[-1]}",
        "match": "imperium.ahlfeldt.se/places/",
    },
    "idref": {
        "url": lambda curie: f"http://www.idref.fr/{curie.split(':')[-1]}",
        "match": "/www.idref.fr/",
    },
    "isni": {
        "url": lambda curie: f"http://isni.org/isni/{curie.split(':')[-1]}",
        "match": "/isni.org/isni/",
    },
    "linz": {
        "url": lambda curie: f"http://gazetteer.linz.govt.nz/place/{curie.split(':')[-1]}",
        "match": "/gazetteer.linz.govt.nz/place/",
    },
    "lgd": {
        "url": lambda curie: f"http://linkedgeodata.org/triplify/{curie.split(':')[-1]}",
        "match": "linkedgeodata.org/triplify/",
    },
    "loc": {
        "url": lambda curie: f"http://id.loc.gov/rwo/agents/{curie.split(':')[-1]}",
        "match": "/id.loc.gov/rwo/agents/",
    },
    "logainm": {
        "url": lambda curie: f"http://logainm.ie/{curie.split(':')[-1]}",
        "match": "logainm.ie/",
    },
    "mesh": {
        "url": lambda curie: f"http://id.nlm.nih.gov/mesh/{curie.split(':')[-1]}",
        "match": "/id.nlm.nih.gov/mesh/",
    },
    "mindat": {
        "url": lambda curie: f"http://www.mindat.org/{curie.split(':')[-1]}",
        "match": "/www.mindat.org/",
    },
    "nalt": {
        "url": lambda curie: f"http://lod.nal.usda.gov/nalt/{curie.split(':')[-1]}",
        "match": "/lod.nal.usda.gov/nalt/",
    },
    "ndl": {
        "url": lambda curie: f"http://id.ndl.go.jp/auth/ndlna/{curie.split(':')[-1]}",
        "match": "/id.ndl.go.jp/auth/ndlna/",
    },
    "permid": {
        "url": lambda curie: f"http://permid.org/{curie.split(':')[-1]}",
        "match": "/permid.org/",
    },
    "pleiades": {
        "url": lambda curie: f"http://pleiades.stoa.org/places/{curie.split(':')[-1]}",
        "match": "/pleiades.stoa.org/places/",
    },
    "stw": {
        "url": lambda curie: f"http://zbw.eu/stw/descriptor/{curie.split(':')[-1]}",
        "match": "zbw.eu/stw/descriptor/",
    },
    "tgn": {
        "url": lambda curie: f"http://vocab.getty.edu/tgn/{curie.split(':')[-1]}",
        "match": "/vocab.getty.edu/tgn/",
    },
    "unesco": {
        "url": lambda curie: f"http://vocabularies.unesco.org/thesaurus/{curie.split(':')[-1]}",
        "match": "/vocabularies.unesco.org/thesaurus/",
    },
    "un": {
        "url": lambda curie: f"http://metadata.un.org/thesaurus/{curie.split(':')[-1]}",
        "match": "/metadata.un.org/thesaurus/",
    },
    "usgs": {
        "url": lambda curie: f"http://edits.nationalmap.gov/apps/gaz-domestic/public/{curie.split(':')[-1]}",
        "match": "/edits.nationalmap.gov/apps/gaz-domestic/public/",
    },
    "viaf": {
        "url": lambda curie: f"http://viaf.org/viaf/{curie.split(':')[-1]}",
        "match": "viaf.org/viaf/",
    },
    "wd": {
        "url": lambda curie: f"http://www.wikidata.org/entity/{curie.split(':')[-1]}",
        "match": "wikidata.org/",
    },
    "worldcat": {
        "url": lambda curie: f"http://id.oclc.org/worldcat/entity/{curie.split(':')[-1]}",
        "match": "/id.oclc.org/worldcat/entity/",
    },
    "yago": {
        "url": lambda curie: f"http://yago-knowledge.org/resource/{curie.split(':')[-1]}",
        "match": "/yago-knowledge.org/resource/",
    },
    "yso": {
        "url": lambda curie: f"http://www.yso.fi/onto/yso/{curie.split(':')[-1]}",
        "match": "/www.yso.fi/onto/yso/",
    },
}
