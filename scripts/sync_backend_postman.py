"""Maintain review regression examples without reading private Postman files."""
from app.schemas.users import UserQuery

GROUP = 'Backend review regressions (isolated QA)'


def augment(collection, request):
    collection['item'] = [item for item in collection['item'] if item['name'] != GROUP]
    params = []
    for name, field in UserQuery.model_fields.items():
        value = str((field.examples or [field.default])[0])
        if name == 'id':
            value = '{{standard_user_id}}'
        if value in ('True', 'False'):
            value = value.lower()
        params.append(dict(key=name, value=value, disabled=name not in ('page', 'page_size', 'order_by', 'order_direction'),
                           description=field.description))
    items = [request('REVIEW users - Optional public filters', 'GET', '/users', 200, token='admin_token', params=params)]
    enabled = [dict(key='role', value='standard'), dict(key='is_active', value='false'),
               dict(key='username_pattern', value='%qa%'), dict(key='order_by', value='username'),
               dict(key='order_direction', value='asc'), dict(key='page', value='1'), dict(key='page_size', value='50')]
    items.append(request('REVIEW users - Enabled combined filters', 'GET', '/users', 200, token='admin_token', params=enabled,
        scripts=['pm.test("AND filters",()=>{for(const row of pm.response.json().items){pm.expect(row.role).to.eql("standard");pm.expect(row.is_active).to.eql(false);pm.expect(row.username.toLowerCase()).to.include("qa");}});']))
    items.append(request('REVIEW platforms - Access type and URL filters', 'GET', '/platforms', 200,
        params=[dict(key='platform_access_types', value='website'), dict(key='platform_url', value='%example.org%'),
                dict(key='order_by', value='platform_url'), dict(key='order_direction', value='asc')],
        scripts=['pm.test("Access membership and URL pattern",()=>{for(const row of pm.response.json().items){pm.expect(row.platform_access_types).to.include("website");pm.expect(row.platform_url.toLowerCase()).to.include("example.org");}});']))
    items.append(request('REVIEW platforms - Preview access replacement', 'PUT', '/platforms', 200, token='admin_token',
        body={'platform_access_types': ['application', 'website', 'link'], 'platform_url': 'https://example.org/library'},
        params=[dict(key='platform_access_types', value='website'), dict(key='dry_run', value='true')]))
    items.append(request('REVIEW password - Reject short new password', 'PUT', '/users/{{standard_user_id}}/password', 422,
        token='admin_token', body={'new_password': 'short'}))
    for item in items:
        item['request']['description'] += (' See docs/BACKEND_REVIEW.md. Passwords newly set must contain 15–1024 Unicode characters; '
            'existing credentials remain valid. Token attempts are limited to 10/account and 50/client in 300 seconds; '
            '429 LOGIN_THROTTLED includes Retry-After. Perform repeated login checks only against disposable QA.')
    collection['item'].append({'name': GROUP, 'item': items})
    def visit(items):
        for item in items:
            if 'item' in item:
                yield from visit(item['item'])
            else:
                yield item
    for item in visit(collection['item']):
        spec = item['request']
        url = spec['url']
        raw = url['raw'] if isinstance(url, dict) else url
        route = raw.split('{{base_url}}', 1)[-1].split('?', 1)[0]
        if spec['method'] == 'POST' and route == '/token':
            spec['description'] = spec.get('description', '').split('Login admission:', 1)[0].split('QA scenario:', 1)[0].strip()
            spec['description'] += ('\n\nLogin admission: 10 attempts per exact account and 50 per direct client in 300 seconds; '
                'all admitted attempts count. At the limit expect 429 LOGIN_THROTTLED and Retry-After seconds; '
                'wait before retrying. Do repeated-attempt checks only on disposable QA. '
                'Existing passwords remain valid; newly set passwords require 15–1024 Unicode characters. '
                'See docs/BACKEND_REVIEW.md.')
            tests = next(event['script']['exec'] for event in item['event'] if event['listen'] == 'test')
            marker = '// Login throttling response contract'
            if marker not in tests:
                tests.extend([marker,
                    'if (pm.response.code === 429) { pm.test("Bounded login retry",()=>{pm.expect(pm.response.json().error.code).to.eql("LOGIN_THROTTLED");pm.expect(Number(pm.response.headers.get("Retry-After"))).to.be.above(0);}); }'])
        if spec['method'] == 'GET' and route == '/users' and isinstance(url, dict):
            known = {value['key'] for value in url.get('query', [])}
            url['query'] = [value for value in url.get('query', []) if value['key'] in UserQuery.model_fields]
            url['query'].extend(dict(value) for value in params if value['key'] not in known)
        if item['name'].startswith('61 -'):
            # This inherited pagination example belongs to /test, not /users.
            from app.schemas.test import TestQuery
            url['query'] = [value for value in url['query'] if value['key'] in TestQuery.model_fields]
            for value in url['query']:
                if value['key'] == 'id':
                    value['value'] = '{{test_id}}'
