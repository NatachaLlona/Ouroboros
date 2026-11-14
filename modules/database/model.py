"""New-installation baseline 001: declarative, schema-qualified PostgreSQL model.

Logical references in braces are resolved exclusively from validated provisioning.
Every foreign key restricts deletion; historical identities are retained.
"""
from database.settings import TABLES, mapping


def ref(table, column=None, nullable=False):
    return f"{column or 'id_'+table} TEXT{' NOT NULL' if not nullable else ''} REFERENCES {{{table}}}(id_{table}) ON DELETE RESTRICT"


PERSONAL = "personal_name TEXT, personal_description TEXT, personal_comment TEXT"
MONEY = "amount NUMERIC(20,6) NOT NULL CHECK (amount >= 0 AND amount < 'Infinity'::numeric), currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$')"
VISIBILITY = "visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private','shared'))"

MODEL = {
    'test': 'value TEXT NOT NULL',
    'foundation_migration': 'version TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL CHECK (checksum ~ \'^[0-9a-f]{64}$\')',
    'provisioning_registry': 'singleton BOOLEAN NOT NULL DEFAULT true UNIQUE CHECK (singleton), structural_hash TEXT NOT NULL, structural_mapping JSONB NOT NULL',
    'api_user': 'username TEXT NOT NULL UNIQUE, is_active BOOLEAN NOT NULL DEFAULT true, credential_version BIGINT NOT NULL DEFAULT 1 CHECK (credential_version > 0)',
    'api_user_credential': ref('api_user') + ", credential_kind TEXT NOT NULL CHECK (credential_kind IN ('human_password','client_credentials')), secret_hash TEXT NOT NULL CHECK (secret_hash LIKE '$argon2id$%'), revoked_at TIMESTAMPTZ, UNIQUE (id_api_user, id_api_user_credential)",
    'app_user': 'personal_name TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT true',
    'app_user_api': ref('app_user')+', '+ref('api_user')+', valid_from TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, valid_until TIMESTAMPTZ, CHECK (valid_until IS NULL OR valid_until > valid_from), UNIQUE (id_app_user, id_api_user, valid_from), UNIQUE (id_app_user, id_api_user, id_app_user_api)',
    'app_user_external_reference': ref('app_user')+', '+ref('api_user', 'id_integration')+', external_identifier TEXT NOT NULL, UNIQUE (id_integration, external_identifier)',
    'role': "name TEXT NOT NULL UNIQUE CHECK (name <> 'super_administrator'), description TEXT",
    'permission': "resource TEXT NOT NULL CHECK (resource <> 'installation_plan'), action TEXT NOT NULL CHECK (action IN ('create','read','update','delete')), UNIQUE (resource, action)",
    'api_user_role': ref('api_user')+', '+ref('role')+', UNIQUE (id_api_user, id_role)',
    'role_permission': ref('role')+', '+ref('permission')+', UNIQUE (id_role, id_permission)',
    'super_administrator': ref('app_user')+', '+ref('api_user')+', '+ref('app_user_api')+', singleton BOOLEAN NOT NULL DEFAULT true UNIQUE CHECK (singleton), UNIQUE (id_api_user), FOREIGN KEY (id_app_user, id_api_user, id_app_user_api) REFERENCES {app_user_api}(id_app_user, id_api_user, id_app_user_api) ON DELETE RESTRICT',
    'plan': 'plan_number INTEGER NOT NULL UNIQUE CHECK (plan_number > 0), name TEXT NOT NULL UNIQUE',
    'module': "name TEXT NOT NULL UNIQUE CHECK (name IN ('database','api_integration','frontend','assistance')), is_mandatory BOOLEAN NOT NULL, CHECK (is_mandatory = (name IN ('database','api_integration')))",
    'plan_module': ref('plan')+', '+ref('module')+', UNIQUE (id_plan, id_module)',
    'installation_plan': ref('plan')+', '+ref('api_user', 'changed_by')+', effective_from TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, effective_until TIMESTAMPTZ, CHECK (effective_until IS NULL OR effective_until > effective_from)',
    'operator_setting': 'name TEXT NOT NULL UNIQUE, minimum_value NUMERIC NOT NULL, maximum_value NUMERIC NOT NULL, current_value NUMERIC NOT NULL, CHECK (minimum_value <= maximum_value AND current_value BETWEEN minimum_value AND maximum_value)',
    'access_rule': ref('api_user', nullable=True)+", rule_kind TEXT NOT NULL CHECK (rule_kind IN ('allow','deny')), resource TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN ('create','read','update','delete')), UNIQUE NULLS NOT DISTINCT (id_api_user, rule_kind, resource, action)",
    'work_classification': 'name TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, description TEXT, tier BIGINT NOT NULL CHECK (tier > 0), UNIQUE (tier) DEFERRABLE INITIALLY DEFERRED',
    'work': ref('work_classification', nullable=True)+", title TEXT NOT NULL, title_language TEXT NOT NULL, synopsis TEXT, verification_state TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_state IN ('unverified','verified','rejected'))",
    'platform': 'name TEXT NOT NULL, description TEXT, is_paid BOOLEAN NOT NULL DEFAULT false, supports_episodes BOOLEAN NOT NULL DEFAULT false, supports_duration BOOLEAN NOT NULL DEFAULT false, url TEXT',
    'work_availability': ref('work')+', '+ref('platform')+", duration_minutes NUMERIC CHECK (duration_minutes > 0 AND duration_minutes < 'Infinity'::numeric), episode_quantity BIGINT CHECK (episode_quantity > 0), url TEXT, UNIQUE (id_work, id_platform), UNIQUE (id_work, id_work_availability)",
    'work_title_alias': ref('work')+', title TEXT NOT NULL, language TEXT NOT NULL, UNIQUE (id_work, title, language)',
    'work_external_reference': ref('work')+', source TEXT NOT NULL, external_identifier TEXT NOT NULL, UNIQUE (source, external_identifier)',
    'user_work': ref('app_user')+', '+ref('work')+', '+PERSONAL+', UNIQUE (id_app_user, id_work)',
    'user_platform': ref('app_user')+', '+ref('platform')+', '+PERSONAL+', UNIQUE (id_app_user, id_platform)',
    'watch_list_entry': ref('app_user')+', '+ref('work')+', id_work_availability TEXT, '+ref('work_classification', nullable=True)+', '+PERSONAL+', added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, added_at_timezone TEXT, FOREIGN KEY (id_app_user, id_work) REFERENCES {user_work}(id_app_user, id_work) ON DELETE RESTRICT, FOREIGN KEY (id_work, id_work_availability) REFERENCES {work_availability}(id_work, id_work_availability) ON DELETE RESTRICT, UNIQUE (id_app_user, id_work), UNIQUE (id_app_user, id_work, id_watch_list_entry)',
    'watch_history': ref('app_user')+', '+ref('work')+', id_work_availability TEXT, '+ref('work_classification', nullable=True)+', '+PERSONAL+', started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, source_timezone TEXT, source_offset TEXT, access_until TIMESTAMPTZ, CHECK (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at), FOREIGN KEY (id_app_user, id_work) REFERENCES {user_work}(id_app_user, id_work) ON DELETE RESTRICT, FOREIGN KEY (id_work, id_work_availability) REFERENCES {work_availability}(id_work, id_work_availability) ON DELETE RESTRICT, UNIQUE (id_app_user, id_work, id_watch_history)',
    'work_submission': ref('app_user')+', '+ref('work', nullable=True)+", submitted_title TEXT NOT NULL, source TEXT, external_identifier TEXT, state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','accepted','rejected'))",
    'work_match_review': ref('work_submission')+', '+ref('work', 'id_candidate_work')+", confidence NUMERIC CHECK (confidence BETWEEN 0 AND 1), state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','matched','dismissed')), UNIQUE (id_work_submission, id_candidate_work)",
    'tag': ref('app_user', nullable=True)+', '+VISIBILITY+', id_source_tag TEXT REFERENCES {tag}(id_tag) ON DELETE RESTRICT, name TEXT NOT NULL, display_name TEXT NOT NULL, description TEXT, CHECK (id_app_user IS NOT NULL OR visibility = \'shared\'), CHECK (id_source_tag IS DISTINCT FROM id_tag), UNIQUE NULLS NOT DISTINCT (id_app_user, name)',
    'tag_category': ref('app_user', nullable=True)+', '+VISIBILITY+", name TEXT NOT NULL, display_name TEXT NOT NULL, description TEXT, CHECK (id_app_user IS NOT NULL OR visibility = 'shared'), UNIQUE NULLS NOT DISTINCT (id_app_user, name)",
    'tag_category_relationship': ref('app_user', nullable=True)+', '+ref('tag')+', '+ref('tag_category')+', UNIQUE (id_tag, id_tag_category)',
    'tag_relationship': ref('app_user', nullable=True)+', '+ref('tag', 'id_source_tag')+', '+ref('tag', 'id_target_tag')+', relationship_kind TEXT NOT NULL, CHECK (id_source_tag <> id_target_tag), UNIQUE (id_source_tag, id_target_tag, relationship_kind)',
    'work_tag': ref('app_user')+', '+ref('work')+', '+ref('tag')+', '+VISIBILITY+', id_watch_list_entry TEXT, id_watch_history TEXT, CHECK (id_watch_list_entry IS NULL OR id_watch_history IS NULL), FOREIGN KEY (id_app_user, id_work) REFERENCES {user_work}(id_app_user, id_work) ON DELETE RESTRICT, FOREIGN KEY (id_app_user, id_work, id_watch_list_entry) REFERENCES {watch_list_entry}(id_app_user, id_work, id_watch_list_entry) ON DELETE RESTRICT, FOREIGN KEY (id_app_user, id_work, id_watch_history) REFERENCES {watch_history}(id_app_user, id_work, id_watch_history) ON DELETE RESTRICT, UNIQUE (id_app_user, id_work, id_tag)',
    'platform_plan': ref('platform')+', name TEXT NOT NULL, '+MONEY+", periodicity TEXT NOT NULL CHECK (periodicity IN ('weekly','monthly','yearly')), UNIQUE (id_platform, id_platform_plan)",
    'platform_promotion': ref('platform')+', name TEXT NOT NULL, '+MONEY+', starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL, CHECK (ends_at > starts_at), UNIQUE (id_platform, id_platform_promotion)',
    'platform_subscription': ref('app_user')+', '+ref('platform')+', id_platform_plan TEXT NOT NULL, '+PERSONAL+', starts_at TIMESTAMPTZ NOT NULL, access_until TIMESTAMPTZ NOT NULL, CHECK (access_until >= starts_at), FOREIGN KEY (id_app_user, id_platform) REFERENCES {user_platform}(id_app_user, id_platform) ON DELETE RESTRICT, FOREIGN KEY (id_platform, id_platform_plan) REFERENCES {platform_plan}(id_platform, id_platform_plan) ON DELETE RESTRICT, UNIQUE (id_app_user, id_platform_subscription), UNIQUE (id_app_user, id_platform, id_platform_subscription)',
    'subscription_charge': ref('app_user')+', '+ref('platform')+', id_platform_subscription TEXT NOT NULL, id_platform_promotion TEXT, '+MONEY+', paid_at TIMESTAMPTZ NOT NULL, access_from TIMESTAMPTZ NOT NULL, access_until TIMESTAMPTZ NOT NULL, CHECK (access_until >= access_from), FOREIGN KEY (id_app_user, id_platform, id_platform_subscription) REFERENCES {platform_subscription}(id_app_user, id_platform, id_platform_subscription) ON DELETE RESTRICT, FOREIGN KEY (id_platform, id_platform_promotion) REFERENCES {platform_promotion}(id_platform, id_platform_promotion) ON DELETE RESTRICT',
    'subscription_reminder': ref('app_user')+', id_platform_subscription TEXT NOT NULL, remind_at TIMESTAMPTZ NOT NULL, acknowledged_at TIMESTAMPTZ, FOREIGN KEY (id_app_user, id_platform_subscription) REFERENCES {platform_subscription}(id_app_user, id_platform_subscription) ON DELETE RESTRICT',
    'api_audit_log': ref('api_user', nullable=True)+', '+ref('app_user', nullable=True)+', transaction_id BIGINT NOT NULL DEFAULT txid_current(), event_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, resource TEXT NOT NULL, target_id TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN (\'INSERT\',\'UPDATE\',\'DELETE\')), UNIQUE (transaction_id, id_api_audit_log)',
    'record_version': ref('api_audit_log')+', resource TEXT NOT NULL, record_id TEXT NOT NULL, version_number BIGINT NOT NULL CHECK (version_number > 0), operation TEXT NOT NULL CHECK (operation IN (\'INSERT\',\'UPDATE\',\'DELETE\')), UNIQUE (resource, record_id, version_number)',
}

# Dependencies determine creation order; references are also checked by PostgreSQL.
ORDER = ['test', 'foundation_migration', 'provisioning_registry', 'api_user', 'api_user_credential',
         'app_user', 'app_user_api', 'app_user_external_reference', 'role', 'permission',
         'api_user_role', 'role_permission', 'super_administrator', 'plan', 'module', 'plan_module',
         'installation_plan', 'operator_setting', 'access_rule', 'work_classification', 'work',
         'platform', 'work_availability', 'work_title_alias', 'work_external_reference',
         'user_work', 'user_platform', 'watch_list_entry', 'watch_history', 'work_submission',
         'work_match_review', 'tag', 'tag_category', 'tag_category_relationship', 'tag_relationship',
         'work_tag', 'platform_plan', 'platform_promotion', 'platform_subscription',
         'subscription_charge', 'subscription_reminder', 'api_audit_log', 'record_version']
CATALOGUE = {'work', 'platform', 'work_availability', 'work_classification', 'tag', 'tag_category',
             'tag_category_relationship', 'tag_relationship', 'work_tag', 'watch_list_entry', 'watch_history'}
PROTECTED = {'provisioning_registry', 'foundation_migration', 'super_administrator', 'plan', 'module',
             'plan_module', 'installation_plan', 'operator_setting', 'api_audit_log', 'record_version'}


def render(text, document):
    """Resolve trusted logical identifiers, including reference column suffixes."""
    import re
    names = mapping(document)
    text = re.sub(r'\{([a-z_]+)\}', lambda match: f'"{document["schema"]}"."{names[match[1]]}"', text)
    for logical in sorted(names, key=len, reverse=True):
        # Placeholders prevent a derived name from being substituted twice.
        text = re.sub(r'\bid_'+logical+r'\b', '__COLUMN_'+logical.upper()+'__', text)
    for logical, physical in names.items():
        text = text.replace('__COLUMN_'+logical.upper()+'__', 'id_'+physical)
    return text


def table_sql(logical, document):
    physical = mapping(document)[logical]
    prefix = document['prefixes'][logical]
    digits = document['base_quantity_digits']
    metadata = f"""sequence_{physical} BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE CHECK (sequence_{physical} > 0),
      prefix_{physical} TEXT NOT NULL DEFAULT '{prefix}' CHECK (prefix_{physical} = '{prefix}'),
      id_{physical} TEXT GENERATED ALWAYS AS (prefix_{physical} || lpad(sequence_{physical}::text,
        greatest({digits}, length(sequence_{physical}::text)), '0')) STORED PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      created_at_timezone TEXT NOT NULL DEFAULT 'UTC'"""
    if logical in CATALOGUE:
        metadata += f", fantasy_name_{physical} TEXT NOT NULL DEFAULT '{logical}' CHECK (fantasy_name_{physical} = '{logical}')"
    return f'CREATE TABLE "{document["schema"]}"."{physical}" ({metadata}, {render(MODEL[logical], document)});'


def baseline_sql(document):
    return '\n'.join(table_sql(table, document) for table in ORDER)
