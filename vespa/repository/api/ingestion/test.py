import gzip, json
from pprint import pprint
from urllib.request import urlopen

url = 'https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.gz'

with urlopen(url) as r:
    with gzip.GzipFile(fileobj=r) as f:
        for j, ln in enumerate(f):
            if ln == b'[\n' or ln == b']\n':
                continue
            if ln.endswith(b',\n'):  # all but the last element
                obj = json.loads(ln[:-2])
            else:
                obj = json.loads(ln)

            print(obj['id'], end=' ')

            pprint(obj)


            if j == 5: break