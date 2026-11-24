ALTER TABLE passage ADD COLUMN IF NOT EXISTS index_corpus VARCHAR(64);
CREATE INDEX IF NOT EXISTS passage_index_corpus ON passage (index_corpus);
