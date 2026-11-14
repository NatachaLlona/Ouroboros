"""Validated form suggestions and bounded read intents; no catalogue writes."""
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, TypeAdapter, ValidationError
from shared.schemas.catalogue import RESOURCES
from shared.text_limits import DESCRIPTION_MAX_LENGTH

MODEL = 'gpt-5.4'
FieldName = Literal['display_name_work_classifications', 'work_classification_name', 'description_work_classifications', 'tier']
RESOURCE = RESOURCES['work_classifications']


class StrictObject(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ConversationMessage(StrictObject):
    assistant_id: Literal['assistant_2'] = 'assistant_2'
    role: Literal['user', 'assistant']
    content: Annotated[StrictStr, Field(min_length=1, max_length=4000)]


class ClassificationState(StrictObject):
    display_name_work_classifications: Annotated[StrictStr, Field(max_length=8000)]
    work_classification_name: Annotated[StrictStr, Field(max_length=8000)]
    description_work_classifications: Annotated[StrictStr, Field(max_length=16000)]
    tier: Annotated[StrictStr, Field(max_length=24)]


class SuggestionRequest(StrictObject):
    assistant_id: Literal['assistant_2'] = 'assistant_2'
    mode: Literal['create', 'edit']
    message: Annotated[StrictStr, Field(min_length=1, max_length=4000)]
    history: Annotated[list[ConversationMessage], Field(max_length=20)]
    values: ClassificationState
    record_id: Annotated[StrictStr, Field(max_length=100)] | None = None
    optional_status: Literal['unoffered', 'offered', 'declined'] = 'unoffered'
    confirmation: Annotated[StrictStr, Field(max_length=100)] | None = None
    technical_visible: StrictBool = False


class ReadQuery(StrictObject):
    resource: Literal['work_classifications']
    search: Annotated[StrictStr, Field(min_length=1, max_length=200)]


class PositionReference(StrictObject):
    search: Annotated[StrictStr, Field(min_length=1, max_length=200)]
    match: Literal['unique', 'first']


class RelativePosition(StrictObject):
    placement: Literal['before', 'after', 'between']
    reference: PositionReference
    second: PositionReference | None


class Proposal(StrictObject):
    field: FieldName
    value: StrictStr | StrictInt | None


class ModelSuggestion(StrictObject):
    reply: StrictStr
    proposals: list[Proposal]
    queries: Annotated[list[ReadQuery], Field(max_length=3)] = []
    relative_position: RelativePosition | None = None
    optional_declined: StrictBool = False


class PositionConfirmation(StrictObject):
    token: StrictStr
    message: StrictStr


class SuggestionResult(ModelSuggestion):
    missing_fields: list[FieldName]
    position_confirmation: PositionConfirmation | None = None
    notice: StrictStr | None = None


class AssistantError(Exception):
    def __init__(self, code):
        super().__init__('Form assistant request could not be completed')
        self.code = code


def validate_suggestion(suggestion, state, mode, maximum_tier):
    """Validate only proposed changes; existing incomplete input remains editable."""
    if not suggestion.reply.strip() or len(suggestion.reply) > 4000 or len(suggestion.proposals) > 4:
        raise AssistantError('ASSISTANT_INVALID_OUTPUT')
    candidate = state.model_dump()
    seen = set()
    proposals = []
    try:
        for proposal in suggestion.proposals:
            if proposal.field in seen:
                raise ValueError
            seen.add(proposal.field)
            value = proposal.value
            # The dropdown represents append with its automatic option, never a cached number.
            if proposal.field == 'tier' and mode == 'create' and type(value) is int and value == maximum_tier:
                value = None
                proposal = proposal.model_copy(update={'value': None})
            if proposal.field == 'tier' and value is None:
                if mode != 'create':
                    raise ValueError
            else:
                field = RESOURCE.create.model_fields[proposal.field]
                annotation = Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
                TypeAdapter(annotation).validate_python(value)
            if proposal.field == 'tier' and value is not None and not 1 <= value <= maximum_tier:
                raise ValueError
            if proposal.field == 'display_name_work_classifications' and (not value.strip() or len(value) > 8000):
                raise ValueError
            candidate[proposal.field] = '' if value is None else str(value)
            proposals.append(proposal)
    except (ValidationError, ValueError, TypeError):
        raise AssistantError('ASSISTANT_INVALID_OUTPUT') from None
    missing = []
    if not candidate['display_name_work_classifications'].strip():
        missing.append('display_name_work_classifications')
    technical = candidate['work_classification_name']
    if not technical and mode == 'create':
        technical = re.sub('[^a-z0-9]+', '_', ''.join(character for character in unicodedata.normalize('NFKD', candidate['display_name_work_classifications']) if not unicodedata.combining(character)).lower()).strip('_')
    if not re.fullmatch('[a-z][a-z0-9]*(_[a-z0-9]+)*', technical):
        missing.append('work_classification_name')
    reply = suggestion.reply
    if 'display_name_work_classifications' in missing:
        reply += '\nWhat is the Display Name?'
    return SuggestionResult(reply=reply, proposals=proposals, missing_fields=missing,
        queries=suggestion.queries, relative_position=suggestion.relative_position,
        optional_declined=suggestion.optional_declined)


