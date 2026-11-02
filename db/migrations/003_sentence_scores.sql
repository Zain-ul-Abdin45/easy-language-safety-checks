-- 003: per-sentence check scores (D4a, D4b, D5) for the v3 pipeline. One row per output sentence and check.
CREATE TABLE IF NOT EXISTS sentence_scores (
  output_sentence_id  int  NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
  check_name          text NOT NULL CHECK (check_name IN ('D4a', 'D4b', 'D5')),
  score               double precision NOT NULL,      -- D4a: mean token log-prob; D4b: lowest changed-span probability (1 if none); D5: min entailment over both directions, or whole source -> sentence if unaligned
  PRIMARY KEY (output_sentence_id, check_name)
);
