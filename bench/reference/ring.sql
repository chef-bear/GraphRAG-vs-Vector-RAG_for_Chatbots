-- Scheme rule from the L5 prompt. Rows: (account_id, scheme_type).
WITH RECURSIVE walk(path, last, amount, lo, hi, len) AS (
  SELECT ARRAY[t.sender_id, t.receiver_id], t.receiver_id, t.amount, t.step::int, t.step::int, 1
  FROM transactions t
  WHERE t.sender_id = %(x)s AND NOT t.is_self_loop
  UNION ALL
  SELECT w.path || t.receiver_id, t.receiver_id, w.amount,
         LEAST(w.lo, t.step), GREATEST(w.hi, t.step), w.len + 1
  FROM walk w
  JOIN transactions t ON t.sender_id = w.last
  WHERE w.last <> %(x)s
    AND t.amount = w.amount
    AND NOT t.is_self_loop
    AND t.step BETWEEN w.hi - %(span)s AND w.lo + %(span)s
    AND ((t.receiver_id = %(x)s AND w.len >= 2)
         OR (w.len < 4 AND NOT t.receiver_id = ANY (w.path)))
),
cycle_members AS (
  SELECT DISTINCT unnest(path) AS account_id FROM walk WHERE last = %(x)s
),
small AS (
  SELECT sender_id, receiver_id, step
  FROM transactions
  WHERE amount < %(cap)s AND NOT is_self_loop
),
targets AS (
  SELECT %(x)s::int AS r
  UNION
  SELECT receiver_id FROM small WHERE sender_id = %(x)s
),
windows AS (
  SELECT DISTINCT s.receiver_id AS r, s.step - d AS w0
  FROM small s
  JOIN targets ON s.receiver_id = targets.r
  CROSS JOIN generate_series(0, %(width)s - 1) AS d
),
grp AS (
  SELECT w.r, array_agg(DISTINCT s.sender_id) AS senders
  FROM windows w
  JOIN small s ON s.receiver_id = w.r AND s.step BETWEEN w.w0 AND w.w0 + %(width)s - 1
  GROUP BY w.r, w.w0
  HAVING count(DISTINCT s.sender_id) >= %(min_senders)s
),
fan_members AS (
  SELECT r AS account_id FROM grp WHERE r = %(x)s OR %(x)s = ANY (senders)
  UNION
  SELECT unnest(senders) FROM grp WHERE r = %(x)s OR %(x)s = ANY (senders)
)
SELECT account_id, 'cycle' AS scheme_type FROM cycle_members
UNION
SELECT account_id, 'fan_in' FROM fan_members
ORDER BY 1, 2;
