# Test the extract_pv_requirements function
from pprint import pprint

from deployment.app.utils import get_pv_requirements


pprint(get_pv_requirements("whg", "../../whg", "whg-staging"))
pprint(get_pv_requirements("vespa", "../../vespa", "vespa"))
