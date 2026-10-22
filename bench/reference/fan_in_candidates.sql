-- per window: senders with exactly one transfer to R in it, below the cap
SELECT DISTINCT receiver_id
FROM (
  SELECT w.w0, t.receiver_id, t.sender_id
  FROM generate_series(%(lo)s, %(hi)s - %(width)s + 1) AS w(w0)
  JOIN transactions t ON t.step BETWEEN w.w0 AND w.w0 + %(width)s - 1
  WHERE NOT t.is_self_loop
  GROUP BY w.w0, t.receiver_id, t.sender_id
  HAVING count(*) = 1 AND max(t.amount) < %(cap)s
) single
GROUP BY w0, receiver_id
HAVING count(*) >= %(min_senders)s
ORDER BY 1;
