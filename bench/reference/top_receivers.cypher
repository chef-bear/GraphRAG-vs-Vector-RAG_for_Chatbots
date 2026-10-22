MATCH (s:Account)-[t:TRANSFER]->(r:Account)
WHERE $a <= t.step <= $b AND s <> r
WITH r, count(DISTINCT s) AS senders
ORDER BY senders DESC, r.account_id ASC
LIMIT $n
RETURN r.account_id
