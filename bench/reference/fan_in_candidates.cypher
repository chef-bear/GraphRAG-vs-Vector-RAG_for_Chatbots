UNWIND range($lo, $hi - $width + 1) AS w
MATCH (s:Account)-[t:TRANSFER]->(r:Account)
WHERE w <= t.step <= w + $width - 1 AND s <> r
WITH w, r, s, count(t) AS n, max(t.amount) AS mx
WHERE n = 1 AND mx < $cap
WITH w, r, count(s) AS senders
WHERE senders >= $min_senders
RETURN DISTINCT r.account_id AS id
ORDER BY id
