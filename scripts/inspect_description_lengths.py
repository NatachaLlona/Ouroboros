"""Read-only, privately authenticated inspection of existing description lengths.

Never writes catalogue data, extracts saved credentials, or prints descriptions
or tokens. Run manually after normal startup; credentials stay in this terminal.
"""
import getpass
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.text_limits import DESCRIPTION_MAX_LENGTH, description_length

ORIGIN = 'http://localhost:6969'
FIELDS = {'tags':'description_tags', 'tag_categories':'description_tag_categories',
          'work_classifications':'description_work_classifications'}


def main():
    username = input('Existing API username: ')
    password = getpass.getpass('Existing API password (not database password): ')
    try:
        data = urlencode({'username':username, 'password':password}).encode()
        with urlopen(Request(ORIGIN+'/token', data=data, headers={'Content-Type':'application/x-www-form-urlencoded'}), timeout=20) as response:
            token = json.load(response)['access_token']
        del password, data
        report = {'limit':DESCRIPTION_MAX_LENGTH, 'resources':{},
                  'note':'Read-only paginated scan, not a transaction snapshot; no catalogue writes.'}
        for table, field in FIELDS.items():
            page, expected, examined, oversized = 1, None, 0, []
            while True:
                query = urlencode({'page':page, 'page_size':50, 'order_by':'id_'+table, 'order_direction':'asc'})
                request = Request(ORIGIN+'/'+table+'?'+query, headers={'Authorization':'Bearer '+token})
                with urlopen(request, timeout=20) as response:
                    result = json.load(response)
                if expected is None:
                    expected = result['count']
                if result['count'] != expected:
                    raise ValueError('Catalogue count changed; rerun inspection')
                for item in result['items']:
                    size = description_length(item[field]) if item[field] is not None else 0
                    if size > DESCRIPTION_MAX_LENGTH:
                        oversized.append({'id':item['id_'+table], 'graphemes':size})
                examined += len(result['items'])
                if examined >= expected:
                    break
                if not result['items']:
                    raise ValueError('Incomplete catalogue scan')
                page += 1
            report['resources'][table] = {'examined':examined, 'over_limit':oversized}
        print(json.dumps(report, indent=2))
    except (HTTPError, URLError, OSError, ValueError, KeyError) as error:
        print('Inspection incomplete: '+type(error).__name__+('. HTTP '+str(error.code) if isinstance(error, HTTPError) else ''))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
