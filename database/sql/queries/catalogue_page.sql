WITH filtered AS NOT MATERIALIZED (
    SELECT {columns} FROM public.{table} WHERE {where}
), page_items AS (
    SELECT {columns} FROM filtered ORDER BY {ordering} LIMIT %s OFFSET %s
)
SELECT (SELECT count(*) FROM filtered), {page_columns}
FROM (SELECT 1) AS anchor LEFT JOIN page_items p ON TRUE
ORDER BY {page_ordering};
