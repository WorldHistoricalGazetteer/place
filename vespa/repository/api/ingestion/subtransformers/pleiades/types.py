from typing import List, Dict, Any


class TypesProcessor:
    def __init__(self, place_types: List[str]):
        """
        :param place_types: List of Pleiades place types (see https://pleiades.stoa.org/vocabularies/place-types).
        """
        self.place_types = place_types

        self.dictionary = {
            "https://pleiades.stoa.org/vocabularies/place-types/abbey": {'AAT': '"300000642"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/abbey-church": {'AAT': '"300007495"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/acropolis": {'AAT': '"300000700"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/agora": {'AAT': '"300008074"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/plaza": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/amphitheatre": {'AAT': '"300007128"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/anchorage": {'AAT': '"300386968"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/aqueduct": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/arch": {'AAT': '"300000994"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/archaeological-site": {'AAT': '"300000810"',
                                                                                       'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/archipelago": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/architecturalcomplex": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/archive-repository": {'AAT': '"300264596"',
                                                                                      'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/barracks": {'AAT': '"300005665"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/basilica": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/bath": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/bay": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/bridge": {'AAT': '"300007836"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/building": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cairn": {'AAT': '"300006960"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/canal": {'AAT': '"300006075"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/canyon": {'AAT': '"300008763"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cape": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cascade": {'AAT': '"300006792"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/castellum": {'AAT': '"300008450"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/castle": {'AAT': '"300006891"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cemetery": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/rapid": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/causeway": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cave": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/centuriation": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/ceramicproduction": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/channel-artificial": {'AAT': '"300133792"',
                                                                                      'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/church-2": {'AAT': '"300007466"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fortified-church": {'AAT': '"300263447"',
                                                                                    'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/church": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/circus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cistern": {'AAT': '"300052558"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/citadel": {'AAT': '"300006902"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/city-block": {'AAT': '"300008077"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/city-center": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/coast": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/coastal-change": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/cultural-landscape": {'AAT': '"300008932"',
                                                                                      'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/dam": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/delta": {'AAT': '"300008760"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/deme-attic": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/desert": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/diocese-church": {'AAT': '"300000799"',
                                                                                  'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/diocese-roman": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/district": {'AAT': '"300000705"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/earthwork": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/ekklesiasterion": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/escarpment": {'AAT': '"300132353"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/estate": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/estuary": {'AAT': '"300266571"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/false": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/farm": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fiction": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/findspot": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fishpond": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/forest": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fort-2": {'AAT': '"300006909"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fort-group": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fort": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fortlet": {'AAT': '"300006910"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/forum": {'AAT': '"300008085"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fountain": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/frontier-system-limes": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/garden-hortus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/city-gate": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/gateway": {'AAT': '"300069189"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/gorge": {'AAT': '"300008767"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/grama": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/grove": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/gymnasium": {'AAT': '"300007297"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/harbor": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/hill": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/hillfort": {'AAT': '"300006911"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/hunting-base": {'AAT': '"300387322"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/island": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/isthmus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/lagoon": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/lake": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/league": {'AAT': '"300387505"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/lighthouse": {'AAT': '"300007741"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/label": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/marsh-wetland": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/metalworking": {'AAT': '"300169784"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/milestone": {'AAT': '"300006973"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/military-base": {'AAT': '"300000455"',
                                                                                 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/military-installation-or-camp-temporary": {'AAT': None,
                                                                                                           'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/mine-2": {'AAT': '"300000390"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/mine": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/monastery": {'AAT': '"300000641"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/monument": {'AAT': '"300006958"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/mosque": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/mountain": {'AAT': '"300008795"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/nome-gr": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/nome-egyptian": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/nuraghe": {'AAT': '"300005727"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/oasis": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/odeon": {'AAT': '"300127075"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/pagus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/palace": {'AAT': '"300005734"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/palace-complex": {'AAT': '"300417317"',
                                                                                  'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/palaistra": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/pass": {'AAT': '"300259572"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/peninsula": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/people": {'AAT': '"300387177"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/piscina-roman": {'AAT': '"300375619"',
                                                                                 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/plain": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/plateau": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/platform": {'AAT': '"300375665"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/polis": {'AAT': '"300008397"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/port": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/postern": {'AAT': '"300002932"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/priory": {'AAT': '"300000645"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/production": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/province-2": {'AAT': '"300000774"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/province": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/pyramid": {'AAT': '"300004838"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/quarry": {'AAT': '"300000402"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/regio-augusti": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/region": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/reservoir": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/ridge": {'AAT': '"300266640"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/mouth": {'AAT': '"300387057"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/river": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/road": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/room": {'AAT': '"300004044"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/ruin": {'AAT': '"300008057"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/salt-pan-salina": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/salt-marsh": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/sanctuary": {'AAT': '"300391482"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/satrapy": {'AAT': '"300235102"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/settlement": {'AAT': '"300008347"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/fortified-settlement": {'AAT': '"300387238"',
                                                                                        'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/settlement-modern": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/sewer": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/shrine": {'AAT': '"300007558"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/siege-mine": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/siege-ramp": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/slag-heap": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/space-exterior-covered": {'AAT': '"300075459"',
                                                                                          'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/space-interior": {'AAT': '"300078790"',
                                                                                  'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/space-uncovered": {'AAT': '"300075460"',
                                                                                   'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/spring": {'AAT': '"300008697"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/stadion": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/state": {'AAT': '"300232420"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/station": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/stoa": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/strait": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/street": {'AAT': '"300008247"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/stupa": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/synagogue": {'AAT': '"300007590"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/taberna-shop": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tell": {'AAT': '"300008545"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/temple-2": {'AAT': '"300007595"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/temple": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/theatre": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tomb": {'AAT': '"300005926"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-division": {'AAT': '"300003615"',
                                                                                  'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-church": {'AAT': '"300003625"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-defensive": {'AAT': '"300004862"',
                                                                                   'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-gate": {'AAT': '"300003627"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-single": {'AAT': '"300004847"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-wall": {'AAT': '"300003639"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-mill": {'AAT': '"300411567"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tower-tomb": {'AAT': '"300120649"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/townhouse": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/treasury": {'AAT': '"300006050"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tribus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tumulus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/tunnel": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/undefined": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/underground-structures": {'AAT': '"300008047"',
                                                                                          'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/unknown": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/unlocated": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/urban": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/valley": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/vicus": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/villa": {'AAT': '"300005517"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/volcano": {'AAT': '"300132325"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/wall-2": {'AAT': '"300002469"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/defensive-wall": {'AAT': '"300002485"',
                                                                                  'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/interior-wall": {'AAT': '"300002535"',
                                                                                 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/city-wall": {'AAT': '"300005072"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/wall": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/water-inland": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/water-feature": {'AAT': '"300180674"',
                                                                                 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/wheel": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/water-open": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/watercourse": {'AAT': '"300387091"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/waterfall": {'AAT': '"300008736"', 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/well": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/whirlpool": {'AAT': None, 'GeoNames': None},
            "https://pleiades.stoa.org/vocabularies/place-types/ziggurat": {'AAT': '"300007626"', 'GeoNames': None},
        }

    def process(self) -> Dict[str, Any]:
        types = [self.dictionary.get(pt, {}).get("AAT") for pt in self.place_types if pt]
        classes = [self.dictionary.get(pt, {}).get("GeoNames") for pt in self.place_types if pt]

        return {
            **({"types": types} if types else {}),
            **({"classes": classes} if classes else {}),
        }
