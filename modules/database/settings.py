"""Strict JSONC configuration and stable logical-to-physical naming."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re


class ConfigurationError(ValueError):
    """Safe, value-free configuration diagnostic."""


TABLES = {
    'test': 'QA', 'foundation_migration': 'FM', 'provisioning_registry': 'PR',
    'api_user': 'AU', 'api_user_credential': 'AC', 'app_user': 'US',
    'app_user_api': 'UA', 'app_user_external_reference': 'UR',
    'role': 'RO', 'permission': 'PE', 'api_user_role': 'AR', 'role_permission': 'RP',
    'super_administrator': 'SA', 'plan': 'PN', 'module': 'MD', 'plan_module': 'PM',
    'installation_plan': 'IP', 'operator_setting': 'OS', 'access_rule': 'AX',
    'work': 'WK', 'platform': 'PL', 'work_availability': 'AV',
    'work_classification': 'WC', 'work_title_alias': 'TA', 'work_external_reference': 'WR',
    'user_work': 'UW', 'user_platform': 'UP', 'watch_list_entry': 'WL', 'watch_history': 'WH',
    'work_submission': 'SB', 'work_match_review': 'MR', 'tag': 'TG', 'tag_category': 'TC',
    'tag_category_relationship': 'CR', 'tag_relationship': 'TR', 'work_tag': 'WT',
    'platform_plan': 'PP', 'platform_subscription': 'PS', 'subscription_charge': 'SC',
    'platform_promotion': 'PX', 'subscription_reminder': 'SR',
    'api_audit_log': 'AL', 'record_version': 'RV',
}
CONFIRMED = {k: TABLES[k] for k in ('api_user', 'app_user', 'test', 'foundation_migration')}


def strip_comments(source):
    """Replace comments with whitespace, retaining offsets for surgical repairs."""
    result = list(source)
    position = 0
    quoted = False
    while position < len(source):
        char = source[position]
        if quoted:
            if char == '\\':
                position += 2
                continue
            if char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif source[position:position+2] in ('//', '/*'):
            block = source[position:position+2] == '/*'
            end = source.find('*/' if block else '\n', position+2)
            if end < 0:
                if block:
                    raise ConfigurationError('Unterminated JSONC comment')
                end = len(source)
            elif block:
                end += 2
            for index in range(position, end):
                if result[index] not in '\r\n':
                    result[index] = ' '
            position = end
            continue
        position += 1
    return ''.join(result)


def read_jsonc(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ConfigurationError('Duplicate JSONC key')
            result[key] = value
        return result
    try:
        return json.loads(strip_comments(Path(path).read_text(encoding='utf-8-sig')),
                          object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, ValueError) as error:
        if isinstance(error, ConfigurationError):
            raise
        raise ConfigurationError('Invalid or unreadable JSONC configuration') from None


def exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        raise ConfigurationError(label + ': missing or unknown fields')


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ConfigurationError(label + ': invalid integer')


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', value) or value.startswith('pg_'):
        raise ConfigurationError('Identifiers must use 1-40 lowercase ASCII letters, digits or underscores')
    return value


def mapping(document):
    vocabulary = {group: document['vocabulary'][group]['name'] for group in ('work', 'platform', 'tag', 'activity')}
    result = {}
    for logical in TABLES:
        if logical.startswith('watch_'):
            physical = vocabulary['activity'] + logical[5:]
        else:
            physical = '_'.join(vocabulary.get(part, part) for part in logical.split('_'))
        # Technical identity, authorization, product, audit and foundation names stay fixed.
        if logical not in DERIVED:
            physical = logical
        if len(physical) > 40:
            raise ConfigurationError('Derived table name exceeds 40 ASCII characters')
        result[logical] = physical
    if len(set(result.values())) != len(result):
        raise ConfigurationError('Derived physical table names collide')
    return result


DERIVED = {key for key in TABLES if key.startswith(('work', 'platform', 'tag', 'watch_', 'user_work', 'user_platform'))}


def conflicts(document):
    groups = {}
    for table, prefix in document['prefixes'].items():
        groups.setdefault(prefix, []).append(table)
    return [tables for tables in groups.values() if len(tables) > 1]


def validate_provisioning(document, allow_conflicts=False):
    exact(document, ('format_version', 'naming_rules_version', 'database_name', 'schema',
                     'vocabulary', 'base_quantity_digits', 'prefixes'), 'provisioning')
    for key in ('format_version', 'naming_rules_version'):
        integer(document[key], 1, 1, key)
    identifier(document['database_name'])
    identifier(document['schema'])
    if document['schema'] in ('public', 'information_schema'):
        raise ConfigurationError('Use a dedicated application schema')
    integer(document['base_quantity_digits'], 1, 18, 'base_quantity_digits')
    exact(document['vocabulary'], ('work', 'platform', 'tag', 'activity'), 'vocabulary')
    for group in document['vocabulary'].values():
        exact(group, ('name',), 'vocabulary group')
        identifier(group['name'])
    exact(document['prefixes'], TABLES, 'prefixes')
    for value in document['prefixes'].values():
        if type(value) is not str or not re.fullmatch('[A-Z]{2,8}', value):
            raise ConfigurationError('Prefixes must contain 2-8 uppercase ASCII letters')
    for table, prefix in CONFIRMED.items():
        if document['prefixes'][table] != prefix:
            raise ConfigurationError('Confirmed prefix must remain ' + table + '=' + prefix)
    mapping(document)
    if conflicts(document) and not allow_conflicts:
        raise ConfigurationError('Duplicate prefixes: ' + '; '.join(', '.join(group) for group in conflicts(document)))
    return document


def validate_operational(document):
    exact(document, ('master_user', 'secret_file', 'published_address', 'published_port',
                     'startup_timeout_seconds', 'healthcheck'), 'database config')
    identifier(document['master_user'])
    if document['master_user'] in ('ouroboros_owner', 'ouroboros_runtime', 'ouroboros_api_login'):
        raise ConfigurationError('Master user conflicts with a protected SQL role')
    if document['secret_file'] != '.secrets/database_sql_password':
        raise ConfigurationError('secret_file must reference .secrets/database_sql_password')
    if type(document['published_address']) is not str:
        raise ConfigurationError('published_address must be a string')
    address = document['published_address'].strip() or '127.0.0.1'
    try:
        if not ipaddress.ip_address(address).is_loopback:
            raise ValueError
    except ValueError:
        raise ConfigurationError('published_address must be a loopback IP address') from None
    integer(document['published_port'], 6669, 6669, 'published_port')
    integer(document['startup_timeout_seconds'], 10, 3600, 'startup_timeout_seconds')
    exact(document['healthcheck'], ('interval_seconds', 'timeout_seconds', 'retries', 'start_period_seconds'), 'healthcheck')
    for key, value in document['healthcheck'].items():
        integer(value, 0 if key == 'start_period_seconds' else 1, 300, 'healthcheck.'+key)
    return {**document, 'published_address': address}


def structural_identity(document):
    value = {'configuration': document, 'physical_tables': mapping(document)}
    canonical = json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest(), value


def initialize(path, example):
    if not path.exists():
        with path.open('x', encoding='utf-8', newline='') as target:
            target.write(example.read_text(encoding='utf-8'))
    return read_jsonc(path)


def repair_prefix(path, table, prefix):
    """Change only the selected value, leaving all comments and layout intact."""
    if table in CONFIRMED or not re.fullmatch('[A-Z]{2,8}', prefix):
        raise ConfigurationError('Choose an unreserved table and a valid prefix')
    source = path.read_text(encoding='utf-8')
    plain = strip_comments(source)
    match = re.search(r'"' + re.escape(table) + r'"\s*:\s*"([A-Z]+)"', plain)
    if not match:
        raise ConfigurationError('Unable to locate prefix for repair')
    source = source[:match.start(1)] + prefix + source[match.end(1):]
    with path.open('w', encoding='utf-8', newline='') as target:
        target.write(source)
