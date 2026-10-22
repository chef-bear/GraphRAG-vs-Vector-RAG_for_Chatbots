MATCH (s:Account)-[t0:TRANSFER]->(n1:Account)
WHERE $a <= t0.step <= $b AND n1.account_id > s.account_id
MATCH p = (n1)-[ts:TRANSFER*2..4]->(s)
WHERE all(t IN ts WHERE t.amount = t0.amount AND $a <= t.step <= $b)
WITH [s] + nodes(p)[..-1] AS loop
WHERE all(n IN loop[1..] WHERE n.account_id > loop[0].account_id)
  AND all(i IN range(0, size(loop) - 2)
          WHERE all(j IN range(i + 1, size(loop) - 1) WHERE loop[i] <> loop[j]))
RETURN DISTINCT [n IN loop | n.account_id] AS loop
ORDER BY loop
