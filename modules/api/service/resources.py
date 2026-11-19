"""Explicit public business representations, never physical-table CRUD discovery."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, create_model
from shared.datetimes import Instant

Text = Annotated[str, Field(strict=True)]
Boolean = Annotated[bool, Field(strict=True)]
Positive = Annotated[int, Field(strict=True, gt=0)]
Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=6)]
Currency = Annotated[str, Field(pattern=r'^[A-Z]{3}$')]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


def required(kind=Text):
    return kind, ...


def optional(kind=Text, default=None):
    return kind | None, default


PERSONAL_FIELDS = {name:optional() for name in ('personal_name','personal_description','personal_comment')}
SPECS = {
    'test': {'value':required()},
    'work': {'title':required(),'title_language':required(),'synopsis':optional(),'id_work_classification':optional()},
    'platform': {'name':required(),'description':optional(),'is_paid':(Boolean,False),
                 'supports_episodes':(Boolean,False),'supports_duration':(Boolean,False),'url':optional()},
    'work_availability': {'id_work':required(),'id_platform':required(),'duration_minutes':optional(Annotated[Decimal,Field(gt=0,allow_inf_nan=False)]),'episode_quantity':optional(Positive),'url':optional()},
    'work_classification': {'name':required(),'display_name':required(),'description':optional(),'tier':optional(Positive)},
    'work_title_alias': {'id_work':required(),'title':required(),'language':required()},
    'work_external_reference': {'id_work':required(),'source':required(),'external_identifier':required()},
    'user_work': {'id_work':required(),**PERSONAL_FIELDS},
    'user_platform': {'id_platform':required(),**PERSONAL_FIELDS},
    'watch_list_entry': {'id_work':required(),'id_work_availability':optional(),'id_work_classification':optional(),**PERSONAL_FIELDS},
    'watch_history': {'id_work':required(),'id_work_availability':optional(),'id_work_classification':optional(),
                      'started_at':optional(Instant),'finished_at':optional(Instant),'access_until':optional(Instant),**PERSONAL_FIELDS},
    'tag': {'name':required(),'display_name':required(),'description':optional(),'id_source_tag':optional(),
            'visibility':(Literal['private','shared'],'private')},
    'tag_category': {'name':required(),'display_name':required(),'description':optional(),'visibility':(Literal['private','shared'],'private')},
    'tag_relationship': {'id_source_tag':required(),'id_target_tag':required(),'relationship_kind':required()},
    'tag_category_relationship': {'id_tag':required(),'id_tag_category':required()},
    'work_tag': {'id_work':required(),'id_tag':required(),'visibility':(Literal['private','shared'],'private'),
                 'id_watch_list_entry':optional(),'id_watch_history':optional()},
    'platform_plan': {'id_platform':required(),'name':required(),'amount':required(Money),'currency':required(Currency),'periodicity':required(Literal['weekly','monthly','yearly'])},
    'platform_promotion': {'id_platform':required(),'name':required(),'amount':required(Money),'currency':required(Currency),
                           'starts_at':required(Instant),'ends_at':required(Instant)},
    'platform_subscription': {'id_platform':required(),'id_platform_plan':required(),'starts_at':required(Instant),'access_until':required(Instant),**PERSONAL_FIELDS},
    'subscription_charge': {'id_platform':required(),'id_platform_subscription':required(),'id_platform_promotion':optional(),
                            'amount':required(Money),'currency':required(Currency),'paid_at':required(Instant),
                            'access_from':required(Instant),'access_until':required(Instant)},
    'subscription_reminder': {'id_platform_subscription':required(),'remind_at':required(Instant),'acknowledged_at':optional(Instant)},
    'work_submission': {'id_work':optional(),'submitted_title':required(),'source':optional(),'external_identifier':optional()},
}
PERSONAL = {'user_work','user_platform','watch_list_entry','watch_history','tag','tag_category',
            'tag_relationship','tag_category_relationship','work_tag','platform_subscription',
            'subscription_charge','subscription_reminder','work_submission'}
APPEND_ONLY = {'subscription_charge'}
READABLE_SHARED_TAGS = {'tag','tag_category'}


def schemas(resource):
    fields = SPECS[resource]
    replacement = create_model(resource.title().replace('_','')+'Replacement',__base__=StrictBody,**fields)
    # Patch omission is distinct from an explicit null; final merged state is validated.
    partial = create_model(resource.title().replace('_','')+'Patch',__base__=StrictBody,
                           **{name:(kind,None) for name,(kind,_) in fields.items()})
    return replacement,partial


ACTIONS = ('create','read','update','delete')
ADMIN_RESOURCES = ('api_user','permission_assignment','access_rule','operator_setting','api_audit_log','record_version')
