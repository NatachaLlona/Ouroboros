"""Whitelisted business CRUD, ownership predicates and complete replacement semantics."""
from psycopg import sql
from fastapi import HTTPException
from pydantic import ValidationError
from api.service.auth import denied, require
from api.service.resources import PERSONAL, READABLE_SHARED_TAGS, SPECS, schemas


def ownership(resource,actor,read=False):
    if resource not in PERSONAL:
        return sql.SQL('true'),[]
    if actor['person'] is None:
        denied()
    if read and resource in READABLE_SHARED_TAGS:
        return sql.SQL('(id_app_user=%s OR visibility=\'shared\')'),[actor['person']]
    return sql.SQL('id_app_user=%s'),[actor['person']]


def validate_state(resource,data):
    model,_=schemas(resource)
    try:
        result=model.model_validate(data).model_dump()
    except ValidationError:
        raise HTTPException(422,'Editable representation is incomplete or invalid') from None
    for start,end in (('started_at','finished_at'),('starts_at','ends_at'),('starts_at','access_until'),('access_from','access_until')):
        if result.get(start) is not None and result.get(end) is not None and result[end]<result[start]:
            raise HTTPException(422,'End instant must not precede start instant')
    return result


def get(session,actor,resource,identifier,action='read'):
    require(session,actor,resource,action)
    if resource=='work_classification' and action!='read':
        session.execute('SELECT pg_advisory_xact_lock(719230819)')
    predicate,parameters=ownership(resource,actor,read=action=='read')
    query=sql.SQL('SELECT * FROM {} WHERE {}=%s AND {} FOR UPDATE').format(session.table(resource),session.column('id_'+resource),predicate)
    row=session.execute(query,[identifier,*parameters]).fetchone()
    if row is None:
        raise HTTPException(404,'Resource not found')
    return session.canonical(row)


def list_records(session,actor,resource,page,size,query):
    require(session,actor,resource,'read')
    predicate,parameters=ownership(resource,actor,read=True)
    allowed={'page','page_size','id'}
    if set(query)-allowed or any(len(query.getlist(key))!=1 for key in query):
        raise HTTPException(422,'Unknown or duplicate query parameter')
    if 'id' in query:
        predicate=sql.SQL('({}) AND {}=%s').format(predicate,session.column('id_'+resource))
        parameters.append(query['id'])
    if page<1 or size<1 or size>session.limits()['page_size']:
        raise HTTPException(422,'Pagination is outside the permitted range')
    count=session.execute(sql.SQL('SELECT count(*) AS count FROM {} WHERE {}').format(session.table(resource),predicate),parameters).fetchone()['count']
    rows=session.execute(sql.SQL('SELECT * FROM {} WHERE {} ORDER BY {} LIMIT %s OFFSET %s').format(session.table(resource),predicate,session.column('sequence_'+resource)),[*parameters,size,(page-1)*size]).fetchall()
    return {'items':[session.canonical(row) for row in rows],'total':count,'page':page,'page_size':size}


def tier_change(session,resource,identifier,data,old=None,deleting=False):
    if resource!='work_classification':
        return
    session.execute('SELECT pg_advisory_xact_lock(719230819)')
    # All affected records are locked, and trigger-generated versions audit each shift.
    records=session.execute('SELECT id_work_classification,tier FROM {work_classification} ORDER BY tier FOR UPDATE').fetchall()
    count=len(records)
    if deleting:
        return
    target=data.get('tier')
    if old is None:
        target=count+1 if target is None else target
        if not 1<=target<=count+1:
            raise HTTPException(422,f'Insertion tier must be between 1 and {count+1}')
        session.execute('UPDATE {work_classification} SET tier=tier+1 WHERE tier>=%s',(target,))
    else:
        if target is None or not 1<=target<=count:
            raise HTTPException(422,f'Tier must be between 1 and {count}')
        previous=old['tier']
        if target<previous:
            session.execute('UPDATE {work_classification} SET tier=tier+1 WHERE tier>=%s AND tier<%s',(target,previous))
        elif target>previous:
            session.execute('UPDATE {work_classification} SET tier=tier-1 WHERE tier>%s AND tier<=%s',(previous,target))
    data['tier']=target


def create(session,actor,resource,data):
    require(session,actor,resource,'create')
    ownership(resource,actor)
    data=validate_state(resource,data)
    tier_change(session,resource,None,data)
    if resource in PERSONAL:
        data['id_app_user']=actor['person']
    columns=list(data)
    query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(session.table(resource),sql.SQL(',').join(session.column(field) for field in columns),sql.SQL(',').join(sql.Placeholder() for _ in columns))
    return session.canonical(session.execute(query,[data[field] for field in columns]).fetchone())


def update(session,actor,resource,identifier,data,partial):
    old=get(session,actor,resource,identifier,'update')
    if partial and not data:
        raise HTTPException(422,'PATCH requires at least one editable field')
    merged={field:old[field] for field in SPECS[resource]} if partial else {}
    merged.update(data)
    result=validate_state(resource,merged)
    tier_change(session,resource,identifier,result,old)
    fields=list(result)
    query=sql.SQL('UPDATE {} SET {} WHERE {}=%s RETURNING *').format(session.table(resource),sql.SQL(',').join(sql.SQL('{}=%s').format(session.column(field)) for field in fields),session.column('id_'+resource))
    return session.canonical(session.execute(query,[result[field] for field in fields]+[identifier]).fetchone())


def delete(session,actor,resource,identifier):
    old=get(session,actor,resource,identifier,'delete')
    tier_change(session,resource,identifier,{},old,deleting=True)
    session.execute(sql.SQL('DELETE FROM {} WHERE {}=%s').format(session.table(resource),session.column('id_'+resource)),(identifier,))
    if resource=='work_classification':
        session.execute('UPDATE {work_classification} SET tier=tier-1 WHERE tier>%s',(old['tier'],))
