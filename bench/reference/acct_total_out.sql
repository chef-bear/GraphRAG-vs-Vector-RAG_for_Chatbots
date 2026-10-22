SELECT COALESCE(SUM(amount), 0)
FROM transactions
WHERE sender_id = %(x)s
  AND step BETWEEN %(a)s AND %(b)s
  AND NOT amount_is_sentinel;
