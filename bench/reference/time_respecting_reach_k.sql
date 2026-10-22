-- (account, step it was reached at, hops); UNION dedups, so the set stays bounded
WITH RECURSIVE reach(account_id, at_step, depth) AS (
  SELECT %(x)s::int, (%(a)s - 1)::int, 0
  UNION
  SELECT t.receiver_id, t.step::int, r.depth + 1
  FROM reach r
  JOIN transactions t ON t.sender_id = r.account_id
  WHERE r.depth < %(k)s AND t.step > r.at_step AND t.step <= %(b)s
)
SELECT DISTINCT account_id FROM reach WHERE account_id <> %(x)s ORDER BY 1;
