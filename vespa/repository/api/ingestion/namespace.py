namespaces = {
    "agrovoc": {
        "url": lambda curie: f"http://aims.fao.org/aos/agrovoc/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?aims\.fao\.org/aos/agrovoc/(?P<id>.*)$",
    },
    "ark": {
        "url": lambda curie: f"http://n2t.net/ark:/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?n2t\.net/ark:/(?P<id>.*)$",
    },
    "bbc": {
        "url": lambda curie: f"http://bbc.co.uk/things/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?bbc\.co\.uk/things/(?P<id>.*)$",
    },
    "bne": {
        "url": lambda curie: f"http://datos.bne.es/resource/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?datos\.bne\.es/resource/(?P<id>.*)$",
    },
    "bnf": {
        "url": lambda curie: f"http://catalogue.bnf.fr/ark:/12148/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?catalogue\.bnf\.fr/ark:/12148/(?P<id>.*)$",
    },
    "cantic": {
        "url": lambda curie: f"http://cantic.bnc.cat/registres/CUCId/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?cantic\.bnc\.cat/registres/CUCId/(?P<id>.*)$",
    },
    "cabi": {
        "url": lambda curie: f"http://id.cabi.org/cabt/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?id\.cabi\.org/cabt/(?P<id>.*)$",
    },
    "dbp": {
        "url": lambda curie: f"http://dbpedia.org/resource/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?dbpedia\.org/resource/(?P<id>.*)$",
    },
    "eurovoc": {
        "url": lambda curie: f"http://eurovoc.europa.eu/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?eurovoc\.europa\.eu/(?P<id>.*)$",
    },
    "emlo": {
        "url": lambda curie: f"http://emlo.bodleian.ox.ac.uk/profile/location/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?emlo\.bodleian\.ox\.ac\.uk/profile/location/(?P<id>.*)$",
    },
    "fast": {
        "url": lambda curie: f"http://id.worldcat.org/fast/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?id\.worldcat\.org/fast/(?P<id>.*)$",
    },
    "gn": {
        "url": lambda curie: f"http://sws.geonames.org/{curie.split(':', 1)[-1]}/",
        "match": r"^https?://(www\.)?sws\.geonames\.org/(?P<id>.*)(?:/)$",
    },
    "gnd": {
        "url": lambda curie: f"http://d-nb.info/gnd/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?d-nb\.info/gnd/(?P<id>.*)$",
    },
    "gesis": {
        "url": lambda curie: f"http://lod.gesis.org/thesoz/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?lod\.gesis\.org/thesoz/(?P<id>.*)$",
    },
    "idref": {
        "url": lambda curie: f"http://idref.fr/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?idref\.fr/(?P<id>.*)$",
    },
    "isni": {
        "url": lambda curie: f"http://isni.org/isni/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?isni\.org/isni/(?P<id>.*)$",
    },
    "ilo": {
        "url": lambda curie: f"http://metadata.ilo.org/thesaurus/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?metadata\.ilo\.org/thesaurus/(?P<id>.*)$",
    },
    "imperium": {
        "url": lambda curie: f"http://imperium.ahlfeldt.se/places/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?imperium\.ahlfeldt\.se/places/(?P<id>.*)$",
    },
    "logainm": {
        "url": lambda curie: f"http://logainm.ie/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?logainm\.ie/(?P<id>.*)$",
    },
    "loc": {
        "url": lambda curie: f"http://id.loc.gov/rwo/agents/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?id\.loc\.gov/rwo/agents/(?P<id>.*)$",
    },
    "linz": {
        "url": lambda curie: f"http://gazetteer.linz.govt.nz/place/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?gazetteer\.linz\.govt\.nz/place//(?P<id>.*)$",
    },
    "mindat": {
        "url": lambda curie: f"http://mindat.org/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?www\.mindat\.org/(?P<id>.*)$",
    },
    "nalt": {
        "url": lambda curie: f"http://lod.nal.usda.gov/nalt/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?lod\.nal\.usda\.gov/nalt/(?P<id>.*)$",
    },
    "ndl": {
        "url": lambda curie: f"http://id.ndl.go.jp/auth/ndlna/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?id\.ndl\.go\.jp/auth/ndlna/(?P<id>.*)$",
    },
    "n2t": {
        "url": lambda curie: f"http://n2t.net/ark:/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?n2t\.net/ark:/(?P<id>.*)$",
    },
    "permid": {
        "url": lambda curie: f"http://permid.org/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?permid\.org/(?P<id>.*)$",
    },
    "pleiades": {
        "url": lambda curie: f"http://pleiades.stoa.org/places/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?pleiades\.stoa\.org/places/(?P<id>.*)$",
    },
    "stwf": {
        "url": lambda curie: f"http://zbw.eu/stw/descriptor/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?zbw\.eu/stw/descriptor/(?P<id>.*)$",
    },
    "tgn": {
        "url": lambda curie: f"http://vocab.getty.edu/tgn/{curie.split(':', 1)[-1].removesuffix('-place')}",
        "match": r"^https?://(www\.)?vocab\.getty\.edu/(.*/)?tgn/(?P<id>.*)(?:-place)?$",
    },
    "viaf": {
        "url": lambda curie: f"http://viaf.org/viaf/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?viaf\.org/viaf/(?P<id>.*)$",
    },
    "wd": {
        "url": lambda curie: f"http://wikidata.org/entity/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?www\.wikidata\.org/entity/(?P<id>.*)$",
    },
    "worldcat": {
        "url": lambda curie: f"http://id.oclc.org/worldcat/entity/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?id\.oclc\.org/worldcat/entity/(?P<id>.*)$",
    },
    "yago": {
        "url": lambda curie: f"http://yago-knowledge.org/resource/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?yago-knowledge\.org/resource/(?P<id>.*)$",
    },
    "yso": {
        "url": lambda curie: f"http://yso.fi/onto/yso/{curie.split(':', 1)[-1]}",
        "match": r"^https?://(www\.)?yso\.fi/onto/yso/(?P<id>.*)$",
    },
}
