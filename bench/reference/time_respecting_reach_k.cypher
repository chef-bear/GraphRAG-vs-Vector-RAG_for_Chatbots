MATCH (x:Account {account_id: $x})-[ts:TRANSFER*1..__K__]->(m:Account)
WHERE all(t IN ts WHERE $a <= t.step <= $b)
  AND all(i IN range(0, size(ts) - 2) WHERE ts[i].step < ts[i + 1].step)
  AND m <> x
RETURN DISTINCT m.account_id AS id
ORDER BY id
