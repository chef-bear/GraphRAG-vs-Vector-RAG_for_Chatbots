MATCH (x:Account {account_id: $x})-[ts:TRANSFER*1..__K__]->(m:Account)
WHERE all(t IN ts WHERE t.amount = $amount AND $a <= t.step <= $b) AND m <> x
RETURN DISTINCT m.account_id AS id
ORDER BY id
