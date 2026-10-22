SELECT receiver_id
FROM transactions
WHERE step BETWEEN %(a)s AND %(b)s AND NOT is_self_loop
GROUP BY receiver_id
ORDER BY count(DISTINCT sender_id) DESC, receiver_id
LIMIT %(n)s;
