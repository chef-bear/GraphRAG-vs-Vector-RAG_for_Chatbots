MATCH (:Account {account_id: $x})-[t:TRANSFER]->()
WHERE $a <= t.step <= $b AND NOT t.amount_is_sentinel
RETURN sum(t.amount)
