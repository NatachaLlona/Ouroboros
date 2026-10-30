"""Public tier and integer-ID CRUD examples; never read private client files."""
from app.schemas.test import TestQuery

GROUP = 'Classification tiers and complete test CRUD (isolated only)'


def augment(collection, request):
    """Append maintained examples while preserving existing request identities."""
    collection['item'] = [item for item in collection['item'] if item['name'] != GROUP]
    known = {item['key'] for item in collection['variable']}
    for name in ('test_record',):
        if name not in known:
            collection['variable'].append(dict(key=name,value='',type='string'))
    params = []
    defaults = dict(page='1',page_size='50',order_by='id',order_direction='asc')
    for key,field in TestQuery.model_fields.items():
        value = defaults.get(key,str((field.examples or ['Europe/Lisbon'])[0]))
        params.append(dict(key=key,value=value,disabled=key not in defaults,description=field.description))
    capture = ['pm.collectionVariables.set("test_id", String(pm.response.json().id));',
               'pm.collectionVariables.set("test_record",JSON.stringify(pm.response.json()));']
    items = [
        request('REMAIN - Test create full record','POST','/test',201,token='standard_token',body={'value':'Isolated CRUD 🐉'},scripts=capture),
        request('REMAIN - Test get integer ID','GET','/test/{{test_id}}',200,token='standard_token',scripts=capture),
        request('REMAIN - Test partial PUT','PUT','/test/{{test_id}}',200,token='standard_token',body={'value':'Changed Unicode 🐉'},scripts=capture),
        request('REMAIN - Test full GET record PUT','PUT','/test/{{test_id}}',200,token='standard_token',body='{{test_record}}',scripts=capture),
        request('REMAIN - Test complete filters and dates','GET','/test',200,token='standard_token',params=params),
        request('REMAIN - Test supervisor update','PUT','/test/{{test_id}}',200,token='supervisor_token',body={'value':'Supervisor individual write'}),
        request('REMAIN - Test standard bulk denied','PUT','/test',403,token='standard_token',body={'value':'Denied'},params=[dict(key='confirm',value='false')]),
        request('REMAIN - Classification bulk tier rejected','PUT','/work_classifications',422,token='admin_token',body={'tier':1},params=[dict(key='confirm',value='true')],scripts=['pm.test("Individual reorder guidance",()=>pm.expect(JSON.stringify(pm.response.json())).to.include("individual PUT"));']),
        request('REMAIN - Classification explicit tier insert (opt-in)','POST','/work_classifications',201,token='supervisor_token',body={'work_classification_name':'isolated_tier_example','display_name_work_classifications':'Tier example','tier':1}),
        request('REMAIN - Classification move tier (opt-in)','PUT','/work_classifications/{{catalogue_id_work_classifications}}',200,token='supervisor_token',body={'tier':1}),
    ]
    for method in ('PUT','DELETE'):
        filters = [dict(key='id',value='{{test_id}}',disabled=True),dict(key='value',value='%Isolated%',disabled=True),
                   dict(key='created_at_from',value='2026-10-01T00:00:00Z',disabled=True),dict(key='created_at_to',value='2026-11-01T00:00:00Z',disabled=True)]
        for actual in (False,True):
            items.append(request('REMAIN - Test ' + method + (' filtered actual (opt-in)' if actual else ' preview'),method,'/test',200,token='admin_token',
                body={'value':'Bulk changed'} if method=='PUT' else None,
                params=[{**p,'disabled':False} if actual and p['key']=='id' else p for p in filters] + [dict(key='confirm' if actual else 'dry_run',value='false' if actual else 'true')]))
    items.append(request('REMAIN - Test delete integer ID (opt-in)','DELETE','/test/{{test_id}}',204,token='standard_token'))
    for item in items:
        if '(opt-in)' in item['name']:
            item['event'].insert(0,dict(listen='prerequest',script=dict(type='text/javascript',exec=[
                'if (pm.variables.get("catalogue_destructive_opt_in") !== "isolated") { pm.execution.skipRequest(); }'])))
    collection['item'].append(dict(name=GROUP,description='Fresh owned QA storage only. Classification tiers are independent positions. Actual test bulk changes require explicit opt-in plus confirm=true. Reorders and deletions are skipped by default.',item=items))
