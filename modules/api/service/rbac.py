"""Sympla-style section/action permissions over Ouroboros' existing SQL model."""
from fastapi import HTTPException

SECTIONS = {
    'identity': ('api_user',),
    'roles': ('role',),
    'authorization': ('permission_assignment', 'access_rule', 'permission'),
    'catalogue': ('test','work','platform','work_availability','work_classification',
                  'work_title_alias','work_external_reference','platform_plan','platform_promotion'),
    'personal': ('user_work','user_platform','watch_list_entry','watch_history','tag',
                 'tag_category','tag_relationship','tag_category_relationship','work_tag','work_submission'),
    'subscriptions': ('platform_subscription','subscription_charge','subscription_reminder'),
    'settings': ('operator_setting',),
    'audit': ('api_audit_log','record_version'),
}
RESOURCE_SECTION = {resource: section for section, resources in SECTIONS.items() for resource in resources}
TO_STORAGE = {'read':'read','write':'create','edit':'update','delete':'delete', 'create':'create','update':'update'}
TO_PUBLIC = {'create':'write','update':'edit','read':'read','delete':'delete'}
PUBLIC_ACTIONS = ('read','write','edit','delete')


def internal(code):
    resource, separator, action = code.partition(':')
    if not separator or resource not in {*SECTIONS, *RESOURCE_SECTION} or action not in TO_STORAGE:
        raise HTTPException(422, 'Unknown permission code; use GET /permissions')
    return resource+':'+TO_STORAGE[action]


def external(code):
    resource, action = code.split(':')
    return resource+':'+TO_PUBLIC[action]


def codes(values):
    normalized = [internal(value) for value in values]
    if len(set(normalized)) != len(normalized):
        raise HTTPException(422, 'Permission codes must be unique')
    return normalized


def covers(scopes, resource, action):
    normalized = {internal(value) for value in scopes if not value.startswith('installation_plan:')}
    return resource+':'+action in normalized or RESOURCE_SECTION.get(resource,resource)+':'+action in normalized


def catalogue():
    return {'items': [
        {'code':section+':'+action,'section':section,'action':action,
         'description':action.title()+' '+section+' records'}
        for section in SECTIONS for action in PUBLIC_ACTIONS
    ]}
