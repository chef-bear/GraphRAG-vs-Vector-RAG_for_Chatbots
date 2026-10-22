-- Created after bulk load (faster than maintaining them during COPY).
CREATE INDEX ON transactions (sender_id, step);
CREATE INDEX ON transactions (receiver_id, step);
CREATE INDEX ON transactions (step);
CREATE INDEX ON transactions (amount);
