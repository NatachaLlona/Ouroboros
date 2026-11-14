SELECT id, value FROM public.test
WHERE (%s::bigint IS NULL OR id = %s)
  AND (%s::text IS NULL OR value ILIKE %s ESCAPE E'\\')
ORDER BY id ASC;
