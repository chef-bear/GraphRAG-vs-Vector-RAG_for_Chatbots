-- walks from x with one amount; a walk ends when it returns to x
WITH RECURSIVE walk(path, last, amount, len) AS (
  SELECT ARRAY[t.sender_id, t.receiver_id], t.receiver_id, t.amount, 1
  FROM transactions t
  WHERE t.sender_id = %(x)s AND t.step BETWEEN %(a)s AND %(b)s AND NOT t.is_self_loop
  UNION ALL
  SELECT w.path || t.receiver_id, t.receiver_id, w.amount, w.len + 1
  FROM walk w
  JOIN transactions t ON t.sender_id = w.last
  WHERE w.last <> %(x)s
    AND t.amount = w.amount
    AND t.step BETWEEN %(a)s AND %(b)s
    AND NOT t.is_self_loop
    AND (t.receiver_id = %(x)s OR (w.len < 4 AND NOT t.receiver_id = ANY (w.path)))
)
SELECT DISTINCT unnest(path) AS account_id FROM walk WHERE last = %(x)s ORDER BY 1;
