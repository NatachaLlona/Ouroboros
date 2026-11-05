WITH page_items AS (
    SELECT id, username, role, is_active, created_at
    FROM public.api_users ORDER BY id LIMIT %s OFFSET %s
)
SELECT (SELECT count(*) FROM public.api_users), p.id, p.username, p.role, p.is_active, p.created_at
FROM (SELECT 1) AS anchor LEFT JOIN page_items p ON TRUE
ORDER BY p.id;
