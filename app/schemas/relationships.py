"""Fixed, one-level identifying projections for collection responses only."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field, create_model


class ReferenceSummary(BaseModel):
    """Public identifying values only; no recursive records or writable fields."""
    model_config = ConfigDict(extra='forbid', frozen=True, json_schema_extra={'readOnly': True})


SUMMARY_FIELDS = {
    'works': ('id_works', 'title', 'title_language', 'fantasy_name_works'),
    'platforms': ('id_platforms', 'platform_name', 'fantasy_name_platforms'),
    'tags': ('id_tags', 'tag_name', 'display_name_tags', 'fantasy_name_tags'),
    'tag_categories': ('id_tag_categories', 'tag_category_name', 'display_name_tag_categories', 'fantasy_name_tag_categories'),
    'work_classifications': ('id_work_classifications', 'work_classification_name',
                             'display_name_work_classifications', 'fantasy_name_work_classifications'),
    'work_availabilities': ('id_work_availabilities', 'id_works', 'id_platforms', 'fantasy_name_work_availabilities'),
    'tag_relationships': ('id_tag_relationships', 'id_tags_source', 'id_tags_target', 'fantasy_name_tag_relationships'),
    'watchlist_entries': ('id_watchlist_entries', 'id_works', 'fantasy_name_watchlist_entries'),
    'watch_history': ('id_watch_history', 'id_works', 'fantasy_name_watch_history'),
}


@dataclass(frozen=True)
class Reference:
    field: str
    table: str
    alias: str


RELATIONSHIPS = {
    'work_availabilities': (Reference('id_works', 'works', 'work'), Reference('id_platforms', 'platforms', 'platform')),
    'tag_category_relationships': (Reference('id_tags', 'tags', 'tag'),
                                   Reference('id_tag_categories', 'tag_categories', 'tag_category')),
    'tag_relationships': (Reference('id_tags_source', 'tags', 'source_tag'), Reference('id_tags_target', 'tags', 'target_tag')),
    'watchlist_entries': (Reference('id_works', 'works', 'work'),
                          Reference('id_work_availabilities', 'work_availabilities', 'work_availability'),
                          Reference('id_work_classifications_predicted', 'work_classifications', 'predicted_classification')),
    'watch_history': (Reference('id_works', 'works', 'work'),
                      Reference('id_work_availabilities', 'work_availabilities', 'work_availability'),
                      Reference('id_work_classifications', 'work_classifications', 'classification')),
    'work_tags': (Reference('id_works', 'works', 'work'), Reference('id_tags', 'tags', 'tag'),
                  Reference('id_tag_relationships', 'tag_relationships', 'tag_relationship'),
                  Reference('id_watchlist_entries', 'watchlist_entries', 'watchlist_entry'),
                  Reference('id_watch_history', 'watch_history', 'watch_history_entry')),
}

SUMMARY_MODELS = {table: create_model(''.join(part.title() for part in table.split('_')) + 'Reference',
    __base__=ReferenceSummary, **{field: (str, Field(json_schema_extra={'readOnly': True})) for field in fields})
    for table, fields in SUMMARY_FIELDS.items()}


def collection_record(table, record):
    """Leave single-record and every write schema unchanged."""
    if table not in RELATIONSHIPS:
        return record
    name = ''.join(part.title() for part in table.split('_'))
    references = create_model(name + 'References', __base__=ReferenceSummary, **{
        reference.alias: (SUMMARY_MODELS[reference.table] | None,
            Field(description='Snapshot identifying values; null when the stored reference is null or unavailable.',
                  json_schema_extra={'readOnly': True})) for reference in RELATIONSHIPS[table]})
    return create_model(name + 'ListItem', __base__=record,
        references=(references, Field(description='Read-only, one-level summaries loaded only for this returned page. '
            'Not accepted by create/update schemas; IDs remain authoritative.', json_schema_extra={'readOnly': True})))
