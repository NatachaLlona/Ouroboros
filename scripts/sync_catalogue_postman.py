"""Maintain public catalogue request examples, Params and opt-in deletion guards.

Run before sync_qa_postman.py and sync_postman_readme.py. Only the canonical
versioned JSON is read; private Postman YAML, metadata and environments are not.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.schemas.catalogue import RESOURCES, PATTERN_HELP
from app.schemas.relationships import RELATIONSHIPS, SUMMARY_FIELDS
from app.text_limits import DESCRIPTION_INPUT_HELP

PATH = ROOT / 'postman/Ouroboros.postman_collection.json'
GROUP = 'Catalogue CRUD (isolated database; supervisor or administrator)'
ROLES = 'Catalogue role scenarios (fresh isolated accounts)'
NEXT = 'Audit, datetime and bulk operations (isolated only)'


def bearer(variable):
    return {'type': 'bearer', 'bearer': [{'key': 'token', 'value': '{{' + variable + '}}', 'type': 'string'}]}


def request(name, method, route, status, token='catalogue_token', body=None, params=None, scripts=()):
    """Build a public request with no credentials or captured runtime values."""
    url = '{{base_url}}' + route
    spec = dict(method=method, header=[], auth=bearer(token), url=url,
                description='Use only an isolated QA database. Captured IDs/tokens stay local. See docs/CATALOGUE_API.md.')
    table = route.strip('/').split('/')[0]
    if table in RESOURCES and any(key.startswith('description_') for key in RESOURCES[table].fields):
        spec['description'] += ' '+DESCRIPTION_INPUT_HELP+' Existing stored descriptions are returned unchanged.'
    if params is not None:
        spec['url'] = {'raw': url, 'host': ['{{base_url}}'], 'path': route.strip('/').split('/'), 'query': params}
    if body is not None:
        spec['header'] = [{'key': 'Content-Type', 'value': 'application/json'}]
        spec['body'] = {'mode': 'raw', 'raw': body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=2),
                        'options': {'raw': {'language': 'json'}}}
    tests = [f'pm.test("HTTP {status}", () => pm.response.to.have.status({status}));',
             'pm.test("Interaction ID", () => pm.expect(pm.response.headers.get("X-Interaction-ID")).to.match(/^[0-9]{24}$/));', *scripts]
    return {'name': name, 'request': spec, 'event': [{'listen': 'test', 'script': {'type': 'text/javascript', 'exec': tests}}]}


def generate(collection):
    """Keep existing requests, append only maintained catalogue folders."""
    collection['item'] = [item for item in collection['item'] if item['name'] not in (GROUP, ROLES, NEXT)]
    variable_names = {v['key'] for v in collection['variable']}
    def variable(name):
        if name not in variable_names:
            collection['variable'].append({'key': name, 'value': '', 'type': 'string'})
            variable_names.add(name)
    for name in ('catalogue_username', 'catalogue_password', 'catalogue_token', 'catalogue_destructive_opt_in',
                 'supervisor_username', 'supervisor_password', 'supervisor_token', 'supervisor_user_id', 'audit_interaction_id'):
        variable(name)
    folders = []
    examples = {
        'works': dict(title='El dragón 🐉', title_language='es', synopsis='An English synopsis.'),
        'platforms': dict(platform_name='QA Library', platform_is_paid=False, platform_is_episodes=True,
                          platform_is_duration_time=True, price_amount=None, price_currency=None,
                          platform_access_types=['application', 'website'], platform_url='https://example.org/library'),
        'work_availabilities': dict(id_works='{{catalogue_id_works}}', id_platforms='{{catalogue_id_platforms}}', duration_minutes='120.5', episode_quantity=3),
        'tags': dict(tag_name='support_without_dependence', display_name_tags='Support 💕', description_tags='Reusable preference tag.'),
        'tag_categories': dict(tag_category_name='relationships', display_name_tag_categories='Vínculos'),
        'tag_category_relationships': dict(id_tags='{{catalogue_id_tags}}', id_tag_categories='{{catalogue_id_tag_categories}}'),
        'tag_relationships': dict(id_tags_source='{{catalogue_id_tags}}', id_tags_target='{{catalogue_id_tags}}'),
        'work_classifications': dict(work_classification_name='qa_classification', display_name_work_classifications='QA only'),
        'watchlist_entries': dict(id_works='{{catalogue_id_works}}', id_work_availabilities='{{catalogue_id_work_availabilities}}', observations='Trailer impressions.'),
        'watch_history': dict(id_works='{{catalogue_id_works}}', id_work_availabilities='{{catalogue_id_work_availabilities}}', watched_at=None, observations='A separate experience.'),
        'work_tags': dict(id_works='{{catalogue_id_works}}', id_tags='{{catalogue_id_tags}}', id_tag_relationships=None,
                          id_watchlist_entries='{{catalogue_id_watchlist_entries}}', id_watch_history=None),
    }
    login = request('CAT - Catalogue login', 'POST', '/token', 200,
        scripts=['pm.collectionVariables.set("catalogue_token", pm.response.json().access_token);'])
    login['request']['auth'] = {'type': 'noauth'}
    login['request']['body'] = {'mode': 'urlencoded', 'urlencoded': [
        {'key': 'username', 'value': '{{catalogue_username}}', 'type': 'text'},
        {'key': 'password', 'value': '{{catalogue_password}}', 'type': 'text'}]}
    for table, resource in RESOURCES.items():
        id_var, record_var = 'catalogue_id_' + table, 'catalogue_record_' + table
        variable(id_var)
        variable(record_var)
        item_path = '/' + table + '/{{' + id_var + '}}'
        capture = [f'pm.collectionVariables.set("{id_var}", pm.response.json().{resource.key});',
                   f'pm.collectionVariables.set("{record_var}", JSON.stringify(pm.response.json()));']
        params = []
        for field in resource.columns:
            value = '{{' + id_var + '}}' if field == resource.key else str(resource.query.model_fields[field].examples[0])
            if value in ('True', 'False'):
                value = value.lower()
            params.append(dict(key=field, value=value, disabled=True, description=resource.query.model_fields[field].description))
        params += [dict(key='page', value='1'), dict(key='page_size', value='50'),
                   dict(key='order_by', value=resource.query.model_fields['order_by'].default, description='Choices: ' + ', '.join(resource.columns)),
                   dict(key='order_direction', value='asc', description='asc or desc; NULLS LAST; ID tie-breaker')]
        for key, schema in resource.query.model_fields.items():
            if key == 'filter_timezone' or key.endswith(('_date', '_from', '_to')):
                params.append(dict(key=key, value=str(schema.examples[0]), disabled=True, description=schema.description))
        params.append(dict(key='display_timezone',value='Europe/Lisbon',disabled=True,description='IANA zone or original; read-only presentation'))
        field = next(iter(resource.fields))
        mutable = {field: examples[table][field]}
        if table == 'works':
            mutable = {'synopsis': 'Updated English synopsis, omitted title preserved.'}
        items = [request(f'CAT {table} - Create', 'POST', '/' + table, 201, body=examples[table], scripts=capture),
            request(f'CAT {table} - Get created ID', 'GET', item_path, 200, scripts=capture),
            request(f'CAT {table} - Partial PUT', 'PUT', item_path, 200, body=mutable, scripts=capture),
            request(f'CAT {table} - Full record PUT', 'PUT', item_path, 200, body='{{' + record_var + '}}', scripts=capture),
            request(f'CAT {table} - List filters and pagination', 'GET', '/' + table, 200, params=params,
                scripts=['pm.test("Page envelope", () => { const p=pm.response.json(); pm.expect(p.count).to.be.a("number"); pm.expect(p.items).to.be.an("array"); pm.expect(p.page).to.eql(1); pm.expect(p.page_size).to.eql(50); });']),
            request(f'CAT {table} - Order descending', 'GET', '/' + table, 200,
                params=[{**p, 'value': 'desc'} if p['key']=='order_direction' else dict(p) for p in params]),
            request(f'CAT {table} - Filter created ID', 'GET', '/' + table, 200,
                params=[dict(p) for p in params],
                scripts=[f'pm.test("Exact ID", () => pm.expect(pm.response.json().items.map(r=>r.{resource.key})).to.eql([pm.collectionVariables.get("{id_var}")]));']),
            request(f'CAT {table} - Delete by ID (opt-in)', 'DELETE', item_path, 204),
            request(f'CAT {table} - ADMIN DELETE ALL (opt-in isolated only)', 'DELETE', '/' + table, 200, token='admin_token',
                params=[dict(key='confirm', value='false', description='Change to true ONLY in an explicitly selected disposable destructive flow.')],
                scripts=['pm.test("Committed count", () => pm.expect(pm.response.json().deleted_count).to.be.a("number"));'])]
        items[6]['event'].insert(0, {'listen': 'prerequest', 'script': {'type': 'text/javascript', 'exec': [
            f'pm.request.url.query.upsert({{key: "{resource.key}", value: pm.collectionVariables.get("{id_var}"), disabled: false}});']}})
        items[6]['request']['description'] += ' This explicitly selected filter demonstration enables the captured ID at runtime; exported optional Params remain unchecked.'
        if table in RELATIONSHIPS:
            projection = {reference.alias: {'field': reference.field, 'fields': list(SUMMARY_FIELDS[reference.table])}
                          for reference in RELATIONSHIPS[table]}
            check = 'const projection = ' + json.dumps(projection) + ';'
            check += ' pm.test("Collection references preserve authoritative IDs and identifying names",()=>{ for(const row of pm.response.json().items){ pm.expect(Object.keys(row.references).sort()).to.eql(Object.keys(projection).sort()); for(const [alias,spec] of Object.entries(projection)){ const ref=row.references[alias]; if(row[spec.field]===null){pm.expect(ref).to.eql(null);}else{pm.expect(Object.keys(ref).sort()).to.eql(spec.fields.slice().sort());pm.expect(ref[spec.fields[0]]).to.eql(row[spec.field]);} } } });'
            for index in (4, 5, 6):
                items[index]['event'][-1]['script']['exec'].append(check)
                items[index]['request']['description'] += ' Collection-only references contain one-level identifying values; single/write records stay unchanged. Remove references before PUT.'
        for item in items[-2:]:
            item['event'].insert(0, {'listen': 'prerequest', 'script': {'type': 'text/javascript', 'exec': [
                'if (pm.variables.get("catalogue_destructive_opt_in") !== "isolated") { pm.execution.skipRequest(); }']}})
            item['request']['description'] += ' Skipped by default. Select this request explicitly on disposable data and set catalogue_destructive_opt_in=isolated locally; DELETE ALL also requires confirm=true. Referenced records return safe 409; never cascade. Delete leaves before parents.'
        folders.append({'name': table, 'item': items})
    collection['item'].append({'name': GROUP, 'description': 'Run login then create/update/list folders in dependency order in a fresh QA database. Deletion requests are skipped unless explicitly opted in; execute leaves before parents. Normal records must never be used.', 'item': [login, *folders]})
    role_items = []
    create = request('CAT roles - Create supervisor', 'POST', '/users', 201, token='admin_token',
        body={'username': '{{supervisor_username}}', 'password': '{{supervisor_password}}', 'role': 'supervisor'},
        scripts=['pm.collectionVariables.set("supervisor_user_id", String(pm.response.json().id));'])
    role_items.append(create)
    for role in ('supervisor', 'standard'):
        item = request(f'CAT roles - Login {role}', 'POST', '/token', 200,
            scripts=[f'pm.collectionVariables.set("{role}_token", pm.response.json().access_token);'])
        item['request']['auth'] = {'type': 'noauth'}
        item['request']['body'] = {'mode': 'urlencoded', 'urlencoded': [dict(key='username', value='{{' + role + '_username}}', type='text'), dict(key='password', value='{{' + role + '_password}}', type='text')]}
        role_items.append(item)
    role_items += [request('CAT roles - Supervisor catalogue read', 'GET', '/works', 200, token='supervisor_token'),
        request('CAT roles - Supervisor DELETE ALL rejected', 'DELETE', '/works', 403, token='supervisor_token', params=[dict(key='confirm', value='false')]),
        request('CAT roles - Standard catalogue rejected', 'GET', '/works', 403, token='standard_token')]
    role_items += [request('CAT roles - Promote standard to supervisor', 'PUT', '/users/{{standard_user_id}}/role', 200,
                          token='admin_token', body={'role': 'supervisor'}),
        request('CAT roles - Promoted existing token reads catalogue', 'GET', '/works', 200, token='standard_token'),
        request('CAT roles - Demote supervisor to standard', 'PUT', '/users/{{standard_user_id}}/role', 200,
                token='admin_token', body={'role': 'standard'}),
        request('CAT roles - Demoted existing token rejected', 'GET', '/works', 403, token='standard_token')]
    works_params = folders[0]['item'][4]['request']['url']['query']
    for item in role_items:
        if item['request']['method'] == 'GET' and item['request']['url'] == '{{base_url}}/works':
            item['request']['url'] = {'raw': '{{base_url}}/works', 'host': ['{{base_url}}'], 'path': ['works'],
                                      'query': [dict(p) for p in works_params]}
        if item['name'] == 'CAT roles - Supervisor DELETE ALL rejected':
            item['event'].insert(0, {'listen': 'prerequest', 'script': {'type': 'text/javascript', 'exec': [
                'if (pm.variables.get("catalogue_destructive_opt_in") !== "isolated") { pm.execution.skipRequest(); }']}})
            item['request']['description'] += ' Opt-in isolated negative check; confirm=false protects against a misconfigured administrator token. Supervisor authorization is rejected before confirmation validation. Enable only the isolated flow locally.'
    collection['item'].append({'name': ROLES, 'description': 'Use fresh isolated administrator/standard accounts from earlier scenarios. Supervisor creation requires fresh private names; never export credentials.', 'item': role_items})
    from app.schemas.audit import AuditFilters
    audit_params = []
    for key, field in AuditFilters.model_fields.items():
        value = {'page':'1','page_size':'50','order_by':'started_at','order_direction':'desc','interaction_id':'{{audit_interaction_id}}',
                 'status':'failure','display_timezone':'original','http_status':'422','actor_id':'1',
                 'started_at_from':'2026-10-01T00:00:00Z','started_at_to':'2026-11-01T00:00:00Z'}.get(key,str((field.examples or [''])[0]))
        audit_params.append(dict(key=key,value=value,disabled=key not in ('page','page_size','order_by','order_direction'),description=field.description or key))
    next_items = [
        request('NEXT - Audit filters and ordering','GET','/api_audit_logs',200,params=audit_params),
        request('NEXT - Original timezone presentation','GET','/watch_history/{{catalogue_id_watch_history}}',200,params=[dict(key='display_timezone',value='original')]),
        request('NEXT - Standard audit denied','GET','/api_audit_logs',403,token='standard_token'),
        request('NEXT - Supervisor bulk PUT denied','PUT','/works',403,token='supervisor_token',body={'synopsis':'Denied'},params=[dict(key='confirm',value='false')]),
        request('NEXT - Missing bulk confirmation','PUT','/works',422,token='admin_token',body={'synopsis':'Not applied'},params=[dict(key='confirm',value='false')]),
        request('NEXT - Unknown filter rejected','DELETE','/works',422,token='admin_token',params=[dict(key='dry_run',value='true'),dict(key='titlle',value='Misspelled')]),
    ]
    for table, resource in RESOURCES.items():
        filters = [dict(key=resource.key,value='{{catalogue_id_' + table + '}}',disabled=True)]
        filters += [dict(key='created_at_from',value='2026-10-01T00:00:00+01:00',disabled=True),dict(key='created_at_to',value='2026-11-01T00:00:00Z',disabled=True)]
        field = next(iter(resource.fields))
        body = {field:examples[table][field]}
        for method in ('PUT','DELETE'):
            next_items.append(request(f'NEXT {table} - {method} preview',''+method,'/'+table,200,token='admin_token',body=body if method=='PUT' else None,
                params=filters + [dict(key='dry_run',value='true')],scripts=['pm.test("Preview count",()=>pm.expect(pm.response.json().matched_count).to.be.a("number"));']))
            actual = request(f'NEXT {table} - {method} filtered actual (opt-in)',method,'/'+table,200,token='admin_token',body=body if method=='PUT' else None,
                params=[{**p,'disabled':False} if p['key']==resource.key else dict(p) for p in filters] + [dict(key='confirm',value='false')])
            actual['event'].insert(0,{'listen':'prerequest','script':{'type':'text/javascript','exec':[
                'if (pm.variables.get("catalogue_destructive_opt_in") !== "isolated") { pm.execution.skipRequest(); }']}})
            next_items.append(actual)
    collection['item'].append({'name':NEXT,'description':'Preview counts can change. Actual bulk mutations require explicit isolated opt-in and confirm=true. Capture an interaction ID, enable its audit filter, and use supervisor/admin to inspect sanitized evidence.', 'item':next_items})
    from scripts.sync_remaining_postman import augment
    augment(collection, request)
    from scripts.sync_batch_postman import augment as augment_batches
    augment_batches(collection, request, examples)
    from scripts.sync_backend_postman import augment as augment_backend
    augment_backend(collection, request)
    # Existing collection GET requests keep their unchecked filters and now expose ordering.
    def visit(items):
        for item in items:
            if 'item' in item:
                yield from visit(item['item'])
            else:
                yield item
    for item in visit(collection['item'][:12]):
        spec = item['request']
        url = spec['url']
        raw = url['raw'] if isinstance(url, dict) else url
        route = raw.split('{{base_url}}', 1)[-1].split('?', 1)[0]
        if spec['method'] != 'GET' or route not in ('/test', '/users'):
            continue
        if not isinstance(url, dict):
            from urllib.parse import parse_qsl
            url = {'raw': raw, 'host': ['{{base_url}}'], 'path': [route.strip('/')],
                   'query': [dict(key=k, value=v) for k,v in parse_qsl(raw.partition('?')[2], keep_blank_values=True)]}
            # Preserve historical string URLs required by equivalent HTTP replay.
            # Structured Params are now required for every collection GET.
            spec['url'] = url
        known = {p['key'] for p in url.setdefault('query', [])}
        supported = [('page', '1'), ('page_size', '50'), ('order_by', 'id'), ('order_direction', 'asc')]
        for key, value in supported:
            if key not in known:
                url['query'].append(dict(key=key, value=value))
        if route == '/test':
            from app.schemas.test import TestQuery
            for key in ('created_at','created_at_timezone','created_at_date','created_at_from','created_at_to','filter_timezone','display_timezone'):
                if key not in known:
                    field = TestQuery.model_fields[key]
                    url['query'].append(dict(key=key,value=str(field.examples[0]),disabled=True,description=field.description))
            for key, value in [('id', '{{test_id}}'), ('value', '%Ouroboros%')]:
                if key not in known:
                    url['query'].append(dict(key=key, value=value, disabled=True))
        for param in url['query']:
            if param['key'] == 'order_by':
                param['description'] = 'Choices: ' + ('id, value, created_at, created_at_timezone' if route == '/test' else 'id, username, role, is_active, created_at')
            elif param['key'] == 'order_direction':
                param['description'] = 'asc or desc; NULLS LAST, unique ID ascending tie-breaker'
    from app.schemas.test import TestQuery
    for item in visit(collection['item']):
        spec = item['request']
        url = spec['url']
        raw = url['raw'] if isinstance(url, dict) else url
        route = raw.split('{{base_url}}', 1)[-1].split('?', 1)[0].strip('/')
        if route not in RESOURCES and route not in ('test', 'api_audit_logs'):
            continue
        if spec['method'] not in ('GET', 'PUT', 'DELETE'):
            continue
        schema = TestQuery if route == 'test' else AuditFilters if route == 'api_audit_logs' else RESOURCES[route].query
        if not isinstance(url, dict):
            url = spec['url'] = dict(raw=raw, host=['{{base_url}}'], path=[route], query=[])
        params = url.setdefault('query', [])
        known = {p['key'] for p in params}
        for param in params:
            key = param['key']
            if key in schema.model_fields and (key == 'filter_timezone' or key.endswith(('_date', '_from', '_to'))):
                param['description'] = schema.model_fields[key].description
        for key, field in schema.model_fields.items():
            if (key == 'filter_timezone' or key.endswith(('_date', '_from', '_to'))) and key not in known:
                params.append(dict(key=key, value=str(field.examples[0]), disabled=True, description=field.description))
    # Keep raw URL and editable Params consistent. Values are URL-encoded once;
    # preserve variable braces so Postman can substitute captured IDs normally.
    from urllib.parse import urlencode
    for item in visit(collection['item']):
        events = item.setdefault('event',[])
        tests = next((event for event in events if event['listen']=='test'),None)
        if tests is None:
            tests={'listen':'test','script':{'type':'text/javascript','exec':[]}}
            events.append(tests)
        scripts = tests['script']['exec']
        marker = '// Central error and interaction contract'
        if marker not in scripts:
            scripts += [marker,
                'if (!pm.request.url.toString().includes("/api_audit_logs")) { pm.collectionVariables.set("audit_interaction_id",pm.response.headers.get("X-Interaction-ID")); }',
                'if (pm.response.code >= 400) { pm.test("Standard error envelope",()=>{ const e=pm.response.json().error; pm.expect(e.code).to.match(/^[A-Z_]+$/); pm.expect(e.interaction_id).to.eql(pm.response.headers.get("X-Interaction-ID")); pm.expect(e.message).to.be.a("string"); }); }']
        url = item['request']['url']
        if isinstance(url, dict) and 'query' in url:
            active = [(p['key'], p['value']) for p in url['query'] if not p.get('disabled', False)]
            url['raw'] = url['raw'].split('?', 1)[0] + ('?' + urlencode(active, safe='{}') if active else '')
    return collection


if __name__ == '__main__':
    collection = generate(json.loads(PATH.read_text(encoding='utf-8')))
    PATH.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Canonical catalogue Postman requests synchronized')
