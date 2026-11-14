-- Request metadata is independent of business/user lifetimes: no actor/target FKs.
CREATE TABLE public.api_audit_logs (
    sequence_api_audit_logs BIGINT GENERATED ALWAYS AS IDENTITY CHECK (sequence_api_audit_logs > 0),
    prefix_api_audit_logs TEXT NOT NULL DEFAULT 'AL' CHECK (prefix_api_audit_logs = 'AL'),
    fantasy_name_api_audit_logs TEXT NOT NULL DEFAULT 'Auditoria de APIs' CHECK (fantasy_name_api_audit_logs = 'Auditoria de APIs'),
    id_api_audit_logs TEXT GENERATED ALWAYS AS (prefix_api_audit_logs || lpad(sequence_api_audit_logs::text,
        greatest(7, length(sequence_api_audit_logs::text)), '0')) STORED PRIMARY KEY,
    interaction_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_ms NUMERIC CHECK (duration_ms >= 0 AND duration_ms < 'Infinity'::numeric),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','success','failure')),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    matched_route TEXT,
    http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
    response_started BOOLEAN NOT NULL DEFAULT false,
    error_code TEXT,
    actor_id BIGINT,
    actor_username TEXT,
    actor_role TEXT,
    request_query JSONB,
    request_body JSONB,
    response_body JSONB,
    resource TEXT,
    target_id TEXT,
    differences JSONB,
    operation_summary TEXT NOT NULL DEFAULT 'Processing API request',
    capture JSONB NOT NULL DEFAULT '{}'::jsonb,
    business_outcome TEXT NOT NULL DEFAULT 'not_started' CHECK (business_outcome IN ('not_started','committed','rolled_back','read_only','preview')),
    mutation_count BIGINT NOT NULL DEFAULT 0 CHECK (mutation_count >= 0),
    mutation_details JSONB
);
CREATE TRIGGER protect_identity BEFORE UPDATE ON public.api_audit_logs
    FOR EACH ROW EXECUTE FUNCTION public.protect_catalogue_identity();
CREATE INDEX ON public.api_audit_logs (started_at);
CREATE INDEX ON public.api_audit_logs (actor_id);
CREATE INDEX ON public.api_audit_logs (resource, target_id);
CREATE INDEX ON public.api_audit_logs (status, http_status);
CREATE INDEX ON public.api_audit_logs (error_code);

CREATE FUNCTION public.api_audit_redact(value jsonb) RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE result jsonb; pair record; item jsonb; normalized text; text_value text; safe_key text;
BEGIN
    IF jsonb_typeof(value) = 'object' THEN
        result := '{}'::jsonb;
        FOR pair IN SELECT * FROM jsonb_each(value) LOOP
            normalized := regexp_replace(lower(pair.key), '[^a-z0-9]', '', 'g');
            safe_key := public.api_audit_redact(to_jsonb(pair.key)) #>> '{}';
            IF normalized ~ '(password|passwd|secret|token|authorization|apikey|credential|privatekey|signingkey|encryptionkey|jwtkey|connectionstring|cookie|hash)' OR normalized IN ('pwd','dsn') THEN
                result := result || jsonb_build_object(safe_key, '[REDACTED]');
            ELSE
                result := result || jsonb_build_object(safe_key, public.api_audit_redact(pair.value));
            END IF;
        END LOOP;
        RETURN result;
    ELSIF jsonb_typeof(value) = 'array' THEN
        result := '[]'::jsonb;
        FOR item IN SELECT * FROM jsonb_array_elements(value) LOOP
            result := result || jsonb_build_array(public.api_audit_redact(item));
        END LOOP;
        RETURN result;
    ELSIF jsonb_typeof(value) = 'string' THEN
        text_value := value #>> '{}';
        IF ltrim(text_value) LIKE '{%' OR ltrim(text_value) LIKE '[%' THEN
            BEGIN
                RETURN to_jsonb(public.api_audit_redact(text_value::jsonb)::text);
            EXCEPTION WHEN invalid_text_representation THEN
                NULL;
            END;
        END IF;
        text_value := regexp_replace(text_value, 'Bearer\s+[^\s"<>]+', '[REDACTED]', 'gi');
        text_value := regexp_replace(text_value, 'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', 'g');
        text_value := regexp_replace(text_value, 'postgres(ql)?://[^\s"<>]+', '[REDACTED]', 'gi');
        IF (SELECT count(*) FROM regexp_matches(text_value, '\m(host|hostaddr|dbname|user|port|password)\s*=', 'gi')) >= 2 THEN
            RETURN to_jsonb('[REDACTED CONNECTION STRING]'::text);
        END IF;
        text_value := regexp_replace(text_value, '\$argon2(id|i|d)\$[^\s"<>]+', '[REDACTED]', 'g');
        RETURN to_jsonb(regexp_replace(text_value, '(password|passwd|pwd|token|secret)\s*[=:]\s*[^\s,;"<>]+', '\1=[REDACTED]', 'gi'));
    END IF;
    RETURN value;
END;
$$;

CREATE FUNCTION public.capture_api_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE audit_id text; old_data jsonb; new_data jsonb; changes jsonb := '{}'::jsonb;
    field_name text; bulk boolean; sensitive boolean; limit_bytes integer; changed_count integer;
BEGIN
    IF current_setting('ouroboros.audit_required', true) IS DISTINCT FROM 'true' THEN
        -- Startup, migrations and direct master SQL are not HTTP API requests.
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
    audit_id := nullif(current_setting('ouroboros.audit_id', true), '');
    IF audit_id IS NULL THEN
        RAISE EXCEPTION 'Required API audit is unavailable' USING ERRCODE = 'P9001';
    END IF;
    bulk := current_setting('ouroboros.audit_bulk', true) = 'true';
    sensitive := current_setting('ouroboros.audit_sensitive', true) = 'true';
    limit_bytes := coalesce(nullif(current_setting('ouroboros.audit_limit', true), '')::integer, 8192);
    old_data := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    new_data := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
    IF TG_TABLE_NAME = 'api_users' THEN
        old_data := jsonb_build_object('id',old_data->'id','username',old_data->'username','role',old_data->'role','is_active',old_data->'is_active','created_at',old_data->'created_at');
        new_data := jsonb_build_object('id',new_data->'id','username',new_data->'username','role',new_data->'role','is_active',new_data->'is_active','created_at',new_data->'created_at');
    END IF;
    IF NOT bulk AND NOT sensitive THEN
        FOR field_name IN SELECT jsonb_object_keys(old_data || new_data) LOOP
            IF old_data->field_name IS DISTINCT FROM new_data->field_name THEN
                changes := changes || jsonb_build_object(field_name, jsonb_build_object('before',old_data->field_name,'after',new_data->field_name));
            END IF;
        END LOOP;
        changes := public.api_audit_redact(changes);
        IF octet_length(changes::text) > limit_bytes THEN changes := NULL; END IF;
    ELSE
        changes := NULL;
    END IF;
    BEGIN
    UPDATE public.api_audit_logs SET
        actor_id = nullif(current_setting('ouroboros.actor_id', true), '')::bigint,
        actor_username = nullif(current_setting('ouroboros.actor_username', true), ''),
        actor_role = nullif(current_setting('ouroboros.actor_role', true), ''),
        resource = TG_TABLE_NAME,
        target_id = CASE WHEN bulk THEN NULL ELSE coalesce(new_data->>('id_' || TG_TABLE_NAME), old_data->>('id_' || TG_TABLE_NAME), new_data->>'id', old_data->>'id') END,
        differences = changes,
        capture = capture || jsonb_build_object('differences',jsonb_build_object('omitted',changes IS NULL,'reason',
            CASE WHEN sensitive THEN 'sensitive_operation' WHEN bulk THEN 'bulk_summary' WHEN changes IS NULL THEN 'capture_limit' ELSE NULL END)),
        business_outcome = 'committed', mutation_count = mutation_count + 1,
        mutation_details = public.api_audit_redact(coalesce(nullif(current_setting('ouroboros.mutation_details', true), '')::jsonb, '{}'::jsonb)),
        operation_summary = CASE WHEN bulk THEN 'Bulk ' ELSE '' END || lower(TG_OP) || ' ' || TG_TABLE_NAME
    WHERE id_api_audit_logs = audit_id;
    GET DIAGNOSTICS changed_count = ROW_COUNT;
    IF changed_count <> 1 THEN
        RAISE EXCEPTION 'Required API audit is unavailable' USING ERRCODE = 'P9001';
    END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION 'Required API audit is unavailable' USING ERRCODE = 'P9001';
    END;
    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
END;
$$;

DO $$
DECLARE resource text;
BEGIN
    FOREACH resource IN ARRAY ARRAY['test','api_users','works','platforms','work_availabilities','tags','tag_categories',
        'tag_category_relationships','tag_relationships','work_tags','work_classifications','watchlist_entries','watch_history']
    LOOP
        EXECUTE format('CREATE TRIGGER api_mutation_audit AFTER INSERT OR UPDATE OR DELETE ON public.%I
            FOR EACH ROW EXECUTE FUNCTION public.capture_api_mutation()', resource);
    END LOOP;
END;
$$;
