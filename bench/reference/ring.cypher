// Scheme rule from the L5 prompt. Rows: (id, type).
MATCH (x:Account {account_id: $x})-[t0:TRANSFER]->(n1:Account)
WHERE n1 <> x
MATCH p = (n1)-[ts:TRANSFER*2..4]->(x)
WHERE all(t IN ts WHERE t.amount = t0.amount AND abs(t.step - t0.step) <= $span)
// (a comprehension directly over `ts` gets mistyped as booleans by Neo4j 5.26)
WITH [x] + nodes(p)[..-1] AS loop, [t0] + ts AS rels
WITH loop, [r IN rels | r.step] AS steps
WHERE all(i IN range(0, size(loop) - 2)
          WHERE all(j IN range(i + 1, size(loop) - 1) WHERE loop[i] <> loop[j]))
  // every pair of steps within $span  <=>  max(step) - min(step) <= $span
  AND all(s1 IN steps WHERE all(s2 IN steps WHERE abs(s1 - s2) <= $span))
UNWIND loop AS n
RETURN DISTINCT n.account_id AS id, 'cycle' AS type
UNION
MATCH (x:Account {account_id: $x})
OPTIONAL MATCH (x)-[small:TRANSFER]->(out:Account)
WHERE small.amount < $cap AND out <> x
WITH x, collect(DISTINCT out) + [x] AS targets
UNWIND targets AS r
MATCH (s:Account)-[t:TRANSFER]->(r)
WHERE t.amount < $cap AND s <> r
WITH r, collect({sender: s.account_id, step: t.step}) AS inflow
UNWIND inflow AS e
UNWIND range(0, $width - 1) AS d
WITH DISTINCT r, inflow, e.step - d AS w0
WITH r, reduce(acc = [], e IN inflow |
       CASE WHEN w0 <= e.step <= w0 + $width - 1 AND NOT e.sender IN acc
            THEN acc + e.sender ELSE acc END) AS senders
WHERE size(senders) >= $min_senders AND (r.account_id = $x OR $x IN senders)
UNWIND senders + [r.account_id] AS id
RETURN DISTINCT id, 'fan_in' AS type
