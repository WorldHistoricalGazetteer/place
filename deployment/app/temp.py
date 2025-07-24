# Test the extract_pv_requirements function
from pprint import pprint

from volume_management import get_pv_requirements

pprint(get_pv_requirements("whg", "../../whg", "whg-staging"))
pprint(get_pv_requirements("vespa", "../../vespa", "vespa"))
