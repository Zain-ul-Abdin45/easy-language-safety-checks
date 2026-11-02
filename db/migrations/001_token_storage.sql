-- 001: store generated token IDs and log-probabilities, the raw output, where lead-in cleaning cut, and a run manifest.
-- Additive only. Existing rows keep NULL in the new columns (dev outputs have no stored token IDs).

ALTER TABLE runs         ADD COLUMN IF NOT EXISTS manifest     jsonb;   -- model revision, library versions, threads, seed, prompt, config hash, git commit
ALTER TABLE base_outputs ADD COLUMN IF NOT EXISTS raw_output   text;    -- decoded model output before cleaning
ALTER TABLE base_outputs ADD COLUMN IF NOT EXISTS clean_cut    int;     -- characters of raw_output removed at the start (lead-in line); output = raw_output[clean_cut:]
ALTER TABLE base_outputs ADD COLUMN IF NOT EXISTS token_source text
  CHECK (token_source IN ('generation', 'retokenized'));              -- 'generation' = IDs kept from the sampling run; 'retokenized' = rebuilt from stored text

-- One row per generated token. logprob is a plain log-softmax (temperature 1) from a teacher-forced pass over these exact IDs,
-- not the temperature-0.3 / top-p scores of generate(). Offsets are character positions in raw_output.
CREATE TABLE IF NOT EXISTS output_tokens (
  base_output_id  int  NOT NULL REFERENCES base_outputs(id) ON DELETE CASCADE,
  position        int  NOT NULL,
  token_id        int  NOT NULL,
  logprob         double precision NOT NULL,
  char_start      int  NOT NULL,
  char_end        int  NOT NULL,
  PRIMARY KEY (base_output_id, position),
  CHECK (char_end >= char_start)
);
