WITH targets AS MATERIALIZED (
    SELECT {key} FROM public.{table} WHERE {where} FOR UPDATE
), changed AS (
    UPDATE public.{table} SET {assignments}
    WHERE {key} IN (SELECT {key} FROM targets) RETURNING 1
)
SELECT (SELECT count(*) FROM targets), (SELECT count(*) FROM changed);
