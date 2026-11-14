"""Allowlisted reads through existing GET routes under the original browser/bearer identity."""
import time
import secrets
import re
import httpx
from shared.form_contracts import AssistantError, PositionConfirmation
from shared.form_adapters import FORM_ADAPTERS
from shared.assistant_identity import ASSISTANT_2


class FormReads:
    assistant_id = ASSISTANT_2
    def __init__(self, request, assistant_id=ASSISTANT_2):
        if assistant_id != self.assistant_id:
            raise AssistantError('ASSISTANT_INVALID_OUTPUT')
        self.request = request

    async def get(self, resource, params=None, record_id=None):
        if resource not in FORM_ADAPTERS['work_classifications'].reads:
            raise AssistantError('ASSISTANT_INVALID_OUTPUT')
        if record_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', record_id):
            raise AssistantError('ASSISTANT_INVALID_OUTPUT')
        path = '/' + resource + ('/' + record_id if record_id is not None else '')
        headers = {name: self.request.headers[name] for name in ('authorization', 'cookie', 'origin', 'sec-fetch-site') if name in self.request.headers}
        # This is an in-process request, not a new connection from the browser's
        # remote IP. Keep its real loopback transport while revalidating the same
        # cookie/bearer through the existing GET authentication and current scopes.
        transport = httpx.ASGITransport(app=self.request.app, client=('127.0.0.1', 0))
        try:
            async with httpx.AsyncClient(transport=transport, base_url=str(self.request.base_url),
                    headers=headers, trust_env=False, follow_redirects=False, timeout=20) as client:
                response = await client.get(path, params=params)
            if response.status_code != 200:
                if response.status_code == 401:
                    raise AssistantError('INVALID_TOKEN')
                if response.status_code == 403:
                    raise AssistantError('INSUFFICIENT_PERMISSIONS')
                raise AssistantError('ASSISTANT_UNAVAILABLE')
            return response.json()
        except (httpx.HTTPError, ValueError, TypeError):
            raise AssistantError('ASSISTANT_UNAVAILABLE') from None

    async def count(self):
        page = await self.get('work_classifications', {'page': 1, 'page_size': 10,
            'order_by': 'tier', 'order_direction': 'asc'})
        return page['count']

    async def search(self, text):
        # Existing ILIKE pattern filter; escape wildcards to search the literal fragment.
        literal = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        items = []
        count = None
        for number in range(1, 101):
            page = await self.get('work_classifications', {'page': number, 'page_size': 50,
                'order_by': 'tier', 'order_direction': 'asc',
                'display_name_work_classifications': '%' + literal + '%'})
            if count is not None and count != page['count']:
                raise AssistantError('ASSISTANT_UNAVAILABLE')
            count = page['count']
            items.extend({key: row[key] for key in ('id_work_classifications',
                'display_name_work_classifications', 'tier')} for row in page['items'])
            if len(items) >= count:
                if len({row['id_work_classifications'] for row in items}) != len(items):
                    raise AssistantError('ASSISTANT_UNAVAILABLE')
                return {'resource': 'work_classifications', 'search': text,
                    'count': count, 'items': items, 'complete': True}
            if not page['items']:
                break
        # Never present truncated observations as complete.
        raise AssistantError('ASSISTANT_UNAVAILABLE')


async def resolve_position(reads, intent, payload):
    anchors = []
    for reference in [intent.reference] + ([intent.second] if intent.second else []):
        result = await reads.search(reference.search)
        rows = [row for row in result['items'] if str(row['id_work_classifications']) != payload.record_id]
        if not rows:
            return None, 'No other classification found for “' + reference.search + '”. Which reference should I use?'
        explicit_first = re.search(r'\b(primeir[oa]|first)\b', payload.message, re.IGNORECASE)
        if (reference.match == 'unique' or not explicit_first) and len(rows) != 1:
            names = ', '.join('“' + row['display_name_work_classifications'] + '” (position ' + str(row['tier']) + ')' for row in rows[:8])
            return None, 'I found multiple matches: ' + names + '. Which one should I use?'
        anchors.append(rows[0])
    if intent.placement == 'between' and len(anchors) != 2:
        return None, 'Which two classifications should this be placed between?'
    current = None
    if payload.mode == 'edit':
        if not payload.record_id:
            return None, 'Reopen the editor to identify the classification.'
        current = await reads.get('work_classifications', record_id=payload.record_id)
    def rank(row):
        return row['tier'] - int(current is not None and current['tier'] < row['tier'])
    if intent.placement == 'between' and (anchors[0]['id_work_classifications'] == anchors[1]['id_work_classifications'] or rank(anchors[1]) != rank(anchors[0]) + 1):
        return None, 'The references are not consecutive in that order. Which one should this be placed before or after?'
    target = rank(anchors[0]) + int(intent.placement in ('after', 'between'))
    maximum = await reads.count() + int(payload.mode == 'create')
    if not 1 <= target <= maximum:
        raise AssistantError('ASSISTANT_UNAVAILABLE')
    names = ' and '.join('“' + row['display_name_work_classifications'] + '” (position ' + str(row['tier']) + ')' for row in anchors)
    placement = {'before': 'before', 'after': 'after', 'between': 'between'}[intent.placement]
    effect = ('Appending does not shift existing classifications.' if target == maximum and payload.mode == 'create'
        else 'Saving changes the order while preserving the relative order of the other classifications.')
    if payload.mode == 'create' and target < maximum:
        effect = 'When saved, the classification at that position and all following classifications shift down.'
    message = f'The matching reference is {names}. Place this classification {placement} {names}, at position {target}? {effect} I will only fill the field; you decide when to save.'
    return {'intent': intent.model_dump(), 'target': target, 'maximum': maximum,
        'anchors': anchors, 'current_tier': current and current['tier'], 'message': message}, None


def remember_position(app, actor, payload, plan):
    plans = getattr(app.state, 'assistant_position_plans', {})
    now = time.monotonic()
    plans = {token: item for token, item in plans.items() if item['expires'] > now}
    if len(plans) >= 128:
        plans.pop(next(iter(plans)))
    token = secrets.token_urlsafe(32)
    plans[token] = {'expires': now + 300, 'assistant_id': payload.assistant_id, 'actor': actor['sub'], 'mode': payload.mode,
        'record_id': payload.record_id, 'plan': plan}
    app.state.assistant_position_plans = plans
    return PositionConfirmation(token=token, message=plan['message'])


def take_position(app, actor, payload):
    item = getattr(app.state, 'assistant_position_plans', {}).pop(payload.confirmation, None)
    if not item or item['expires'] < time.monotonic() or item['assistant_id'] != payload.assistant_id or item['actor'] != actor['sub'] or item['mode'] != payload.mode or item['record_id'] != payload.record_id:
        raise AssistantError('ASSISTANT_INVALID_OUTPUT')
    return item['plan']
