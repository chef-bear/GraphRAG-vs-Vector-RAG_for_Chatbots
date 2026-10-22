-- each loop is found once, from its smallest account (path[1]); later accounts are larger
WITH RECURSIVE walk(path, last, amount, len) AS (
  SELECT ARRAY[t.sender_id, t.receiver_id], t.receiver_id, t.amount, 1
  FROM transactions t
  WHERE t.step BETWEEN %(a)s AND %(b)s AND t.receiver_id > t.sender_id
  UNION ALL
  SELECT w.path || t.receiver_id, t.receiver_id, w.amount, w.len + 1
  FROM walk w
  JOIN transactions t ON t.sender_id = w.last
  WHERE w.last <> w.path[1]
    AND t.amount = w.amount
    AND t.step BETWEEN %(a)s AND %(b)s
    AND ((t.receiver_id = w.path[1] AND w.len >= 2)
         OR (w.len < 4 AND t.receiver_id > w.path[1] AND NOT t.receiver_id = ANY (w.path)))
)
SELECT DISTINCT path[1:len] AS loop FROM walk WHERE last = path[1] ORDER BY 1;
