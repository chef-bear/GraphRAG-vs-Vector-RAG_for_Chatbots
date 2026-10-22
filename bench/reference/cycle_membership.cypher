MATCH (x:Account {account_id: $x})-[t0:TRANSFER]->(n1:Account)
WHERE $a <= t0.step <= $b AND n1 <> x
MATCH p = (n1)-[ts:TRANSFER*1..4]->(x)
WHERE all(t IN ts WHERE t.amount = t0.amount AND $a <= t.step <= $b)
WITH [x] + nodes(p)[..-1] AS loop
WHERE all(i IN range(0, size(loop) - 2)
          WHERE all(j IN range(i + 1, size(loop) - 1) WHERE loop[i] <> loop[j]))
UNWIND loop AS n
RETURN DISTINCT n.account_id AS id
ORDER BY id
