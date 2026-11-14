"""Explicitly enabled form adapters, based on the existing creation schemas."""
from dataclasses import dataclass
from shared.schemas.catalogue import RESOURCES
from shared.text_limits import DESCRIPTION_MAX_LENGTH
from shared.assistant_identity import ASSISTANT_2


@dataclass(frozen=True)
class FormAdapter:
    resource: str
    fields: tuple
    labels: tuple
    generated: tuple
    reads: tuple

    def context(self, payload, maximum):
        schema = RESOURCES[self.resource].create.model_json_schema()
        meanings = {'display_name_work_classifications': 'Human-facing fantasy name, required nonblank text.',
            'work_classification_name': 'Technical identifier; automatically normalized on create, required stored value on edit. Never ask spontaneously.',
            'description_work_classifications': 'Optional faithful explanation of this work-rating classification, not tag categories.',
            'tier': 'Ordered position; automatic append on create or existing position on edit. Manual save reorganizes rather than replaces records.'}
        return {'assistant_id': ASSISTANT_2, 'resource': self.resource, 'mode': payload.mode,
            'fields_in_visual_order': [dict(name=name, label=label,
                validation=schema['properties'][name],
                meaning=meanings[name],
                visible=name not in self.generated or payload.technical_visible,
                required=name in schema.get('required', []),
                required_condition='stored value on edit; valid generated default on create' if name in self.generated else
                    'required on edit; automatic append allowed on create' if name == 'tier' else None,
                generated=name in self.generated) for name, label in zip(self.fields, self.labels)],
            'values': payload.values.model_dump(), 'optional_status': payload.optional_status,
            'defaults': {'tier': 'automatic append in create mode; empty is valid',
                'work_classification_name': 'normalized fantasy name in create mode; preserve existing generator'},
            'description_max_graphemes': DESCRIPTION_MAX_LENGTH,
            'maximum_tier': maximum, 'allowed_get_resources': self.reads}


# Registration's actual rendered order. Other forms remain deliberately disabled.
FORM_ADAPTERS = {'work_classifications': FormAdapter('work_classifications',
    ('display_name_work_classifications', 'work_classification_name', 'description_work_classifications', 'tier'),
    ('Display Name', 'Technical Name', 'Description', 'Position'),
    ('work_classification_name',), ('work_classifications',))}
