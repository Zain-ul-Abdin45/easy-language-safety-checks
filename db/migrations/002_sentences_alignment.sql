-- 002: one sentence table for source and output, alignment stored in both directions, source-sentence IDs for omission tags (codebook v0.3).
-- Additive. The texts.split check gains 'smoke' (throwaway texts for pipeline tests, never labelled, never held-out).

ALTER TABLE texts DROP CONSTRAINT IF EXISTS texts_split_check;
ALTER TABLE texts ADD CONSTRAINT texts_split_check CHECK (split IN ('dev', 'heldout', 'smoke'));

-- Source sentences belong to a text; output sentences to a base output (offsets in the CLEANED output text).
CREATE TABLE IF NOT EXISTS sentences (
  id              serial PRIMARY KEY,
  text_id         text NOT NULL REFERENCES texts(id),
  base_output_id  int  REFERENCES base_outputs(id) ON DELETE CASCADE,   -- NULL = source sentence
  idx             int  NOT NULL,
  char_start      int  NOT NULL,
  char_end        int  NOT NULL,
  body            text NOT NULL,
  has_words       boolean NOT NULL                                      -- false = only punctuation/space (skipped by the checks)
);
CREATE UNIQUE INDEX IF NOT EXISTS sentences_source_uq ON sentences (text_id, idx) WHERE base_output_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS sentences_output_uq ON sentences (base_output_id, idx) WHERE base_output_id IS NOT NULL;

-- Output -> source (D4a unit labels, D5 premise, "no source" = possible insertion). source_sentence_id NULL when the best cosine is below the threshold.
CREATE TABLE IF NOT EXISTS output_alignment (
  output_sentence_id  int PRIMARY KEY REFERENCES sentences(id) ON DELETE CASCADE,
  source_sentence_id  int REFERENCES sentences(id),
  cosine              double precision NOT NULL,                         -- best cosine, also stored when below the threshold
  many_to_one         boolean NOT NULL DEFAULT false                     -- another output sentence has the same source sentence
);

-- Source -> output (unmatched source sentences = candidate omissions; D3). output_sentence_id NULL when the best cosine is below the threshold.
CREATE TABLE IF NOT EXISTS source_alignment (
  base_output_id      int NOT NULL REFERENCES base_outputs(id) ON DELETE CASCADE,
  source_sentence_id  int NOT NULL REFERENCES sentences(id),
  output_sentence_id  int REFERENCES sentences(id),
  cosine              double precision NOT NULL,
  n_output_matches    int NOT NULL DEFAULT 0,                            -- how many output sentences align to this source sentence
  PRIMARY KEY (base_output_id, source_sentence_id)
);

-- Codebook v0.3: an omission tag names the source sentence that lost content. NOT VALID = existing (v0.2.5) rows are not checked, new ones are.
ALTER TABLE harm_annotations ADD COLUMN IF NOT EXISTS source_sentence_id int REFERENCES sentences(id);
ALTER TABLE harm_annotations DROP CONSTRAINT IF EXISTS omission_needs_source_sentence;
ALTER TABLE harm_annotations ADD CONSTRAINT omission_needs_source_sentence
  CHECK (category <> 'omission' OR source_sentence_id IS NOT NULL) NOT VALID;
