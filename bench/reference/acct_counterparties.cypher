MATCH (a:Account {account_id: $x})-[:TRANSFER]->(b:Account)
WHERE b <> a
RETURN count(DISTINCT b)
