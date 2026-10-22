SELECT count(DISTINCT receiver_id)
FROM transactions
WHERE sender_id = %(x)s AND receiver_id <> %(x)s;
