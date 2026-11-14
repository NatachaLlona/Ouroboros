"""Read-only assistant orchestration and relative-position confirmation."""
import re
import unicodedata
from shared.form_contracts import AssistantError, SuggestionResult, RelativePosition, Proposal
from api.form_assistant_reads import remember_position, take_position, resolve_position
from shared.assistant_identity import ASSISTANT_2


def guard_proposals(result, payload):
    text = ''.join(char for char in unicodedata.normalize('NFKD', payload.message.lower()) if not unicodedata.combining(char))
    refusal = r'\b(?:nao|not|never|don.t)\s+(?:quero|preench\w*|alter\w*|mud\w*|ger\w*|cri\w*|change|modify|fill|generate|want)\b.{0,40}'
    technical = bool(re.search(r'nome\s+tecnico|technical\s+name|work_classification_name', text)) and not re.search(
        refusal + r'(nome\s+tecnico|technical\s+name)', text)
    description_refused = re.search(refusal + r'(descri[cç]|description)', text)
    result.proposals = [item for item in result.proposals
        if (item.field != 'work_classification_name' or technical)
        and (item.field != 'description_work_classifications' or not description_refused and
            (not payload.values.description_work_classifications.strip() or re.search(r'descri[cç]|description', text)))]
    return result


async def assist(app, actor, payload, reads, service):
    if payload.assistant_id != ASSISTANT_2:
        raise AssistantError('ASSISTANT_INVALID_OUTPUT')
    maximum = await reads.count() + int(payload.mode == 'create')
    if payload.confirmation:
        old = take_position(app, actor, payload)
        plan, question = await resolve_position(reads, RelativePosition.model_validate(old['intent']), payload)
        if not plan:
            return SuggestionResult(reply=question, notice=question, proposals=[], missing_fields=[])
        if plan != old:
            return SuggestionResult(reply='The order changed. Review it before applying.', proposals=[], missing_fields=[],
                position_confirmation=remember_position(app, actor, payload, plan))
        return SuggestionResult(reply='The position was confirmed for filling; the form has not been saved.',
            proposals=[Proposal(field='tier', value=None if payload.mode == 'create' and plan['target'] == maximum else plan['target'])], missing_fields=[])
    observations = []
    requested = set()
    result = None
    proposals = {}
    declined = False
    for turn in range(3):
        if hasattr(service, 'call'):
            result = await service.suggest(payload, maximum, actor, observations)
        else:
            result = await service.suggest(payload, maximum, observations)
        proposals.update((item.field, item) for item in result.proposals)
        declined = declined or result.optional_declined
        if not result.queries:
            break
        if turn == 2:
            raise AssistantError('ASSISTANT_INVALID_OUTPUT')
        for query in result.queries:
            identity = (query.resource, query.search)
            if identity in requested or len(requested) >= 3:
                raise AssistantError('ASSISTANT_INVALID_OUTPUT')
            requested.add(identity)
            observations.append(await reads.search(query.search))
    result.proposals = list(proposals.values())
    result.optional_declined = declined
    result = guard_proposals(result, payload)
    result.queries = []
    if observations:
        matches = [row for observation in observations for row in observation['items']]
        if matches:
            result.notice = 'Matches found (similarity does not mean equality): ' + ', '.join(
                '“' + row['display_name_work_classifications'] + '” (position ' + str(row['tier']) + ')' for row in matches[:8]) + '.'
        else:
            result.notice = 'No matches found for the requested queries.'
    if result.relative_position:
        result.proposals = [item for item in result.proposals if item.field != 'tier']
        plan, question = await resolve_position(reads, result.relative_position, payload)
        if plan:
            result.position_confirmation = remember_position(app, actor, payload, plan)
            result.reply = plan['message']
        else:
            result.reply = question
            result.notice = question
        result.relative_position = None
    elif re.search(r'\b(antes|depois|entre|primeir[oa]\s+d[oa]s?)\b', payload.message, re.IGNORECASE) and any(item.field == 'tier' for item in result.proposals):
        result.proposals = [item for item in result.proposals if item.field != 'tier']
        result.notice = 'I need to identify the matching reference before suggesting a relative position. Which classification should I use?'
    return result
