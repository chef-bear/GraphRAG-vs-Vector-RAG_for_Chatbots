-- Agent-facing schema (SPEC §4.1). No label columns or tables.
CREATE TABLE accounts (
  account_id      INTEGER PRIMARY KEY,
  customer_id     TEXT NOT NULL,
  init_balance    NUMERIC(14,2) NOT NULL,
  country         TEXT NOT NULL,
  account_type    TEXT NOT NULL,
  behavior_id     SMALLINT NOT NULL
);

CREATE TABLE transactions (
  tx_id               INTEGER PRIMARY KEY,
  sender_id           INTEGER NOT NULL REFERENCES accounts,
  receiver_id         INTEGER NOT NULL REFERENCES accounts,
  tx_type             TEXT NOT NULL,
  amount              NUMERIC(14,2) NOT NULL,
  step                SMALLINT NOT NULL,
  amount_is_sentinel  BOOLEAN NOT NULL,
  is_self_loop        BOOLEAN NOT NULL
);
