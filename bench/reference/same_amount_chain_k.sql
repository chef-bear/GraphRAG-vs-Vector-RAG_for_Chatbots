WITH RECURSIVE reach(account_id, depth) AS (
  SELECT %(x)s::int, 0
  UNION
  SELECT t.receiver_id, r.depth + 1
  FROM reach r
  JOIN transactions t ON t.sender_id = r.account_id
  WHERE r.depth < %(k)s
    AND t.amount = %(amount)s
    AND t.step BETWEEN %(a)s AND %(b)s
)
SELECT DISTINCT account_id FROM reach WHERE account_id <> %(x)s ORDER BY 1;
