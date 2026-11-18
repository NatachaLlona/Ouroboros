"""Custom-role and permission-catalogue HTTP administration."""
from typing import Annotated
from fastapi import Depends, HTTPException, Query, Response
from pydantic import Field, field_validator
from psycopg.types.json import Jsonb
from psycopg import sql
from api.service.resources import StrictBody
from api.service.auth import require
from api.service import rbac

PermissionCode=Annotated[str,Field(strict=True,max_length=100)]


class Permissions(StrictBody):
    permissions:list[PermissionCode]=Field(max_length=128)

    @field_validator('permissions')
    @classmethod
    def valid_permissions(cls,values):
        # Validation uses the same catalogue as token scope/delegation checks.
        return [rbac.external(value) for value in rbac.codes(values)]


class RoleCreate(Permissions):
    name:Annotated[str,Field(strict=True,min_length=1,max_length=80)]
    description:Annotated[str,Field(strict=True,max_length=200)]=''

    @field_validator('name')
    @classmethod
    def printable_name(cls,value):
        if value!=value.strip() or not value.isprintable():
            raise ValueError('Use a trimmed printable role name')
        return value


class RolePatch(StrictBody):
    name:Annotated[str,Field(strict=True,min_length=1,max_length=80)] | None=None
    description:Annotated[str,Field(strict=True,max_length=200)] | None=None


def mutate(session,operation,target,body):
    return next(iter(session.function('api_rbac',operation,target,Jsonb(body)).fetchone().values()))


def role_data(session,identifier):
    row=session.execute("SELECT id_role AS identifier,name,description,is_system,created_at FROM {role} WHERE id_role=%s AND left(name,9)<>'identity_'",(identifier,)).fetchone()
    if row is None:
        raise HTTPException(404,'Role not found')
    result=dict(row)
    result['permissions']=[rbac.external(item['code']) for item in session.execute('SELECT p.resource||\':\'||p.action AS code FROM {role_permission} rp JOIN {permission} p USING(id_permission) WHERE rp.id_role=%s ORDER BY p.resource,p.action',(identifier,))]
    return result


def account_data(session,identifier):
    row=session.execute('SELECT id_api_user AS identifier,id_api_user,username,is_active,created_at FROM {api_user} WHERE id_api_user=%s AND deleted_at IS NULL',(identifier,)).fetchone()
    if row is None:
        raise HTTPException(404,'API identity not found')
    result=dict(row)
    roles=session.execute("SELECT r.id_role AS identifier,r.name FROM {api_user_role} ur JOIN {role} r USING(id_role) WHERE ur.id_api_user=%s AND left(r.name,9)<>'identity_' ORDER BY r.sequence_role",(identifier,)).fetchall()
    result['roles']=[dict(role) for role in roles]
    result['role_identifier']=roles[0]['identifier'] if len(roles)==1 else None
    result['individual_permissions']=[rbac.external(item['code']) for item in session.execute("SELECT p.resource||':'||p.action AS code FROM {api_user_role} ur JOIN {role} r USING(id_role) JOIN {role_permission} rp USING(id_role) JOIN {permission} p USING(id_permission) WHERE ur.id_api_user=%s AND r.name='identity_'||%s ORDER BY p.resource,p.action",(identifier,identifier))]
    query=sql.SQL("SELECT resource||':'||action AS code FROM {} WHERE resource=ANY(%s) AND {}.api_can(%s,resource,action) ORDER BY resource,action").format(session.table('permission'),sql.Identifier(session.store.document['schema']))
    result['permissions']=[rbac.external(item['code']) for item in session.execute(query,(list(rbac.SECTIONS),identifier))]
    return result


def install(app,context):
    @app.get('/permissions',tags=['Authorization'],summary='List independent section/action permissions')
    def permissions(auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'permission','read')
        return rbac.catalogue()

    @app.get('/roles',tags=['Authorization'])
    def roles(page:Annotated[int,Query(ge=1)]=1,page_size:Annotated[int,Query(ge=1)]=10,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','read')
        if page_size>session.limits()['page_size']:
            raise HTTPException(422,'Page size exceeds the permitted limit')
        rows=session.execute("SELECT id_role FROM {role} WHERE left(name,9)<>'identity_' ORDER BY sequence_role LIMIT %s OFFSET %s",(page_size,(page-1)*page_size)).fetchall()
        count=session.execute("SELECT count(*) AS count FROM {role} WHERE left(name,9)<>'identity_'").fetchone()['count']
        return {'items':[role_data(session,row['id_role']) for row in rows],'count':count,'page':page,'page_size':page_size}

    @app.post('/roles',status_code=201,tags=['Authorization'])
    def create(body:RoleCreate,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','create')
        values=body.model_dump()
        values['permissions']=rbac.codes(body.permissions)
        identifier=mutate(session,'role_create',None,values)
        return role_data(session,identifier)

    @app.get('/roles/{identifier}',tags=['Authorization'])
    def detail(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','read')
        return role_data(session,identifier)

    @app.patch('/roles/{identifier}',tags=['Authorization'])
    def patch(identifier:str,body:RolePatch,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','update')
        values=body.model_dump(exclude_unset=True)
        if not values or any(value is None for value in values.values()):
            raise HTTPException(422,'Provide nonnull editable role fields')
        mutate(session,'role_patch',identifier,values)
        return role_data(session,identifier)

    @app.delete('/roles/{identifier}',status_code=204,tags=['Authorization'])
    def remove(identifier:str,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','delete')
        mutate(session,'role_delete',identifier,{})
        return Response(status_code=204)

    @app.put('/roles/{identifier}/permissions',tags=['Authorization'])
    def replace(identifier:str,body:Permissions,auth=Depends(context,scope='function')):
        session,actor=auth
        require(session,actor,'role','update')
        mutate(session,'role_permissions',identifier,{'permissions':rbac.codes(body.permissions)})
        return role_data(session,identifier)
