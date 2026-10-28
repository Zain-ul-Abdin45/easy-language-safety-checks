-- Project 3 experiment database: easylang_p3
-- Answers: how far does each condition reach the memo's success criteria?
-- Re-runnable: drops and recreates the schema p3.

DROP SCHEMA IF EXISTS p3 CASCADE;
CREATE SCHEMA p3;
SET search_path TO p3;

-- ---------- Materials ----------
CREATE TABLE texts (
  id            text PRIMARY KEY,                 -- e.g. T001
  source        text NOT NULL,
  url           text,
  licence       text,
  text_type     text,                             -- procedure, safety, schedule, reporting...
  is_synthetic  boolean NOT NULL DEFAULT false,
  split         text NOT NULL CHECK (split IN ('dev','heldout')),
  body          text NOT NULL,
  word_count    int,
  fkgl          numeric,                          -- source readability, baseline for "gain"
  collected_on  date DEFAULT current_date
);

CREATE TABLE protected_items (                    -- names, dates, numbers, conditions, actions
  id       serial PRIMARY KEY,
  text_id  text NOT NULL REFERENCES texts(id) ON DELETE CASCADE,
  kind     text NOT NULL CHECK (kind IN ('name','date','number','deadline','condition','action','other')),
  value    text NOT NULL
);

-- ---------- Generation ----------
CREATE TABLE runs (
  id              serial PRIMARY KEY,
  model           text NOT NULL,                  -- Qwen/Qwen2.5-1.5B-Instruct
  backend         text NOT NULL,                  -- transformers / ollama
  quantization    text DEFAULT 'none',
  seed            int  NOT NULL,
  temperature     numeric,
  prompt_version  text NOT NULL,
  target_level    text,
  hardware        text,                           -- e.g. 'M3 Pro CPU-only'
  config_frozen   boolean NOT NULL DEFAULT false,
  created_at      timestamptz DEFAULT now(),
  UNIQUE (model, seed, prompt_version)            -- a rerun must not silently double the outputs
);

CREATE TABLE base_outputs (                       -- one per text x run (seed)
  id           serial PRIMARY KEY,
  run_id       int  NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  text_id      text NOT NULL REFERENCES texts(id),
  output       text NOT NULL,
  gen_seconds  numeric,
  peak_mem_mb  numeric,                           -- process maximum so far: run-level, not per output
  truncated    boolean NOT NULL DEFAULT false,    -- generation hit max_new_tokens (possible fake omission)
  UNIQUE (run_id, text_id)
);

CREATE TABLE conditions (
  code         text PRIMARY KEY,
  description  text NOT NULL
);
INSERT INTO conditions VALUES
 ('C1','Baseline: unmodified model output'),
 ('C2','Probability: low-confidence changes reverted'),
 ('C3','Lookup: off-list changes replaced or reverted'),
 ('C4','Lookup + grammar'),
 ('C5','Probability, then lookup, then grammar');

-- ---------- Alignment and checks ----------
CREATE TABLE changed_spans (
  id              serial PRIMARY KEY,
  base_output_id  int NOT NULL REFERENCES base_outputs(id) ON DELETE CASCADE,
  sentence_idx    int,
  source_span     text,
  output_span     text,
  reachable       boolean NOT NULL,               -- false = split/reorder/insertion the checks cannot touch
  probability     numeric,                        -- model probability of the substitute (C2 signal)
  on_wordlist     boolean,                        -- C3 signal
  harmful_gold    boolean,                        -- PRIMARY annotator's label for the January AUC check (NULL = not labelled or fragment)
  discuss         boolean NOT NULL DEFAULT false, -- annotator unsure: flag for the second pass instead of guessing
  fragment        boolean NOT NULL DEFAULT false, -- annotator: diff piece of a rewritten sentence, not a word swap (excluded from AUC)
  labelled_by     text,
  labelled_at     timestamptz
);

-- Every span label from every rater round. changed_spans.harmful_gold holds the primary label only;
-- second-person and consistency labels live here and feed the agreement analysis, never the views.
CREATE TABLE span_labels (
  span_id      int  NOT NULL REFERENCES changed_spans(id) ON DELETE CASCADE,
  annotator    text NOT NULL,
  rater_role   text NOT NULL CHECK (rater_role IN ('primary','second','consistency')),
  harmful      boolean,                           -- NULL when fragment
  fragment     boolean NOT NULL DEFAULT false,
  discuss      boolean NOT NULL DEFAULT false,
  labelled_at  timestamptz DEFAULT now(),
  PRIMARY KEY (span_id, annotator, rater_role)
);

CREATE TABLE span_actions (
  span_id     int  NOT NULL REFERENCES changed_spans(id) ON DELETE CASCADE,
  condition   text NOT NULL REFERENCES conditions(code),
  action      text NOT NULL CHECK (action IN ('keep','revert','replace','flag')),
  final_span  text,
  PRIMARY KEY (span_id, condition)
);

CREATE TABLE condition_outputs (
  id                   serial PRIMARY KEY,
  base_output_id       int  NOT NULL REFERENCES base_outputs(id) ON DELETE CASCADE,
  condition            text NOT NULL REFERENCES conditions(code),
  output               text NOT NULL,
  word_count           int  NOT NULL,
  fkgl                 numeric,
  protected_preserved  int,
  protected_total      int,
  post_seconds         numeric DEFAULT 0,          -- time added by the checks
  flagged              boolean DEFAULT false,      -- sent to human review
  blind_id             uuid DEFAULT gen_random_uuid(), -- what annotators see
  UNIQUE (base_output_id, condition)
);

-- ---------- Annotation (blind) ----------
CREATE TABLE harm_annotations (
  id                   serial PRIMARY KEY,
  condition_output_id  int  NOT NULL REFERENCES condition_outputs(id) ON DELETE CASCADE,
  annotator            text NOT NULL,
  rater_role           text NOT NULL DEFAULT 'primary' CHECK (rater_role IN ('primary','second','consistency')),
                                                   -- only 'primary' rows are counted in the views (no double counting)
  category             text NOT NULL CHECK (category IN
                        ('meaning_change','omission','wrong_number_date_name','hallucination',
                         'altered_condition','unclear_reference','repetition','other')),
  output_quote         text,                       -- smallest wrong piece, copied from the output by the rater
  quote_occurrence     int,                        -- which occurrence of the quote (1-based); required when it occurs more than once
  reachable            boolean NOT NULL,           -- computed on import: quote <= max_span_tokens words and overlaps a reachable changed span
  severity             int CHECK (severity BETWEEN 1 AND 3),
  note                 text,
  created_at           timestamptz DEFAULT now()
);

-- One row per output a rater has reviewed, including outputs with no error ("none"), so that
-- "reviewed, no harm" can be told apart from "not reviewed yet".
CREATE TABLE output_reviews (
  condition_output_id  int  NOT NULL REFERENCES condition_outputs(id) ON DELETE CASCADE,
  annotator            text NOT NULL,
  rater_role           text NOT NULL CHECK (rater_role IN ('primary','second','consistency')),
  reviewed_at          timestamptz DEFAULT now(),
  PRIMARY KEY (condition_output_id, annotator, rater_role)
);

-- Non-harm flags per output: insufficient simplification (tracked apart from harm) and "discuss".
CREATE TABLE output_flags (
  id                   serial PRIMARY KEY,
  condition_output_id  int  NOT NULL REFERENCES condition_outputs(id) ON DELETE CASCADE,
  annotator            text NOT NULL,
  rater_role           text NOT NULL DEFAULT 'primary' CHECK (rater_role IN ('primary','second','consistency')),
  kind                 text NOT NULL CHECK (kind IN ('simplicity_lexical','simplicity_structural','discuss')),
  created_at           timestamptz DEFAULT now()
);

-- ---------- Criteria (fill thresholds before the held-out run) ----------
CREATE TABLE success_criteria (
  key          text PRIMARY KEY,
  threshold    numeric,
  description  text NOT NULL
);
INSERT INTO success_criteria VALUES
 ('min_simplification_kept', 0.80, 'PRELIMINARY: C5 keeps at least this share of C1 readability gain (confirm before held-out)'),
 ('auc_go_lower',            0.50, 'GO if the lower bound of the text-level bootstrap interval of the dev AUC is above this'),
 ('tau_max_harmless_reverted', 0.20, 'PRELIMINARY: tau for C2 is set on dev as the largest value that reverts at most this share of harmless (labelled n) dev spans'),
 ('max_simplicity_flag_increase', 0.10, 'PRELIMINARY: C5 may have at most this many percentage points more outputs flagged for insufficient simplification than C1 (human guard, independent of FKGL)'),
 ('auc_inconclusive_point',  0.60, 'INCONCLUSIVE if AUC point estimate is at least this but the lower bound is not above auc_go_lower'),
 ('max_post_seconds',        NULL, 'Optional: max extra seconds per text the checks may add');

-- ---------- Project feasibility ----------
CREATE TABLE milestones (
  month           text PRIMARY KEY,
  sort            int  NOT NULL,
  planned_hours   int  NOT NULL,
  main_output     text NOT NULL,
  done            boolean NOT NULL DEFAULT false
);
INSERT INTO milestones VALUES
 ('November',1,140,'Review draft, terminology, data plan, protocol',false),
 ('December',2, 60,'Model running locally, first baseline',false),
 ('January', 3,160,'Checks implemented, go/no-go of probability signal, pilot ready',false),
 ('February',4,200,'Pilot across all five conditions',false),
 ('March',   5,200,'Analysis and March review',false),
 ('April',   6,140,'Submission and reproducibility package',false);

CREATE TABLE work_log (
  id      serial PRIMARY KEY,
  day     date NOT NULL DEFAULT current_date,
  month   text NOT NULL REFERENCES milestones(month),
  hours   numeric NOT NULL CHECK (hours >= 0),
  task    text NOT NULL
);

-- ================= Views: "to what extent can we achieve it?" =================

-- Exact per-condition metrics (no double counting of words).
CREATE VIEW v_condition_metrics AS
WITH per_output AS (
  SELECT co.id, co.condition, r.seed, t.split, co.word_count, co.fkgl, t.fkgl AS src_fkgl,
         co.protected_preserved, co.protected_total, co.post_seconds, b.gen_seconds, b.peak_mem_mb, co.flagged,
         EXISTS (SELECT 1 FROM output_reviews o WHERE o.condition_output_id = co.id AND o.rater_role = 'primary') AS reviewed,
         -- harm = severity 2-3 (codebook v0.2.4); severity 1 tags are minor notes, kept in harms_all for the sensitivity check
         (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id = co.id AND h.rater_role = 'primary' AND h.severity >= 2) AS harms,
         (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id = co.id AND h.rater_role = 'primary' AND h.severity >= 2 AND h.reachable) AS harms_reach,
         (SELECT count(*) FROM harm_annotations h WHERE h.condition_output_id = co.id AND h.rater_role = 'primary')                    AS harms_all
  FROM condition_outputs co
  JOIN base_outputs b ON b.id = co.base_output_id
  JOIN runs r ON r.id = b.run_id
  JOIN texts t ON t.id = b.text_id
)
SELECT condition, seed, split,
       count(*)                                                   AS n_outputs,
       -- harm rates use REVIEWED outputs only (numerator and words); the other columns use all outputs
       round(100.0 * sum(harms)       FILTER (WHERE reviewed) / NULLIF(sum(word_count) FILTER (WHERE reviewed),0), 3) AS harm_per_100w,
       round(100.0 * sum(harms_reach) FILTER (WHERE reviewed) / NULLIF(sum(word_count) FILTER (WHERE reviewed),0), 3) AS reachable_harm_per_100w,
       round(sum(protected_preserved)::numeric / NULLIF(sum(protected_total),0), 3) AS preservation_rate,
       round(avg(src_fkgl - fkgl), 2)                             AS mean_fkgl_gain,
       round(avg(gen_seconds + post_seconds), 2)                  AS mean_seconds_per_text,
       round(max(peak_mem_mb), 0)                                 AS peak_mem_mb,
       round(avg(flagged::int), 3)                                AS share_flagged,
       count(*) FILTER (WHERE reviewed)                           AS n_reviewed,
       round(100.0 * sum(harms_all)   FILTER (WHERE reviewed) / NULLIF(sum(word_count) FILTER (WHERE reviewed),0), 3) AS harm_all_tags_per_100w
FROM per_output
GROUP BY condition, seed, split;

-- Share of changed spans the word-level checks can reach.
CREATE VIEW v_reach AS
SELECT r.seed, t.split,
       count(*)                                   AS changed_spans,
       round(avg(cs.reachable::int), 3)           AS share_reachable
FROM changed_spans cs
JOIN base_outputs b ON b.id = cs.base_output_id
JOIN runs r ON r.id = b.run_id
JOIN texts t ON t.id = b.text_id
GROUP BY r.seed, t.split;

-- January go/no-go: AUC of the probability signal (low probability should mean harmful).
-- Mann-Whitney formulation: P(prob_harmless > prob_harmful), ties count half.
-- POINT ESTIMATE ONLY. The bootstrap interval over texts and the go / inconclusive / no-go decision
-- (protocol section 6) are computed by src/auc_decision.py, which also prints in the pilot report.
-- Fragments (f) and unlabelled spans are excluded.
CREATE VIEW v_probability_auc AS
WITH s2 AS (
  SELECT cs.id, b.text_id
  FROM changed_spans cs
  JOIN base_outputs b ON b.id = cs.base_output_id
  JOIN texts t ON t.id = b.text_id
  WHERE t.split = 'dev' AND cs.reachable AND NOT cs.fragment
    AND cs.harmful_gold IS NOT NULL AND cs.probability IS NOT NULL
), s AS (
  SELECT cs.probability, cs.harmful_gold
  FROM changed_spans cs
  JOIN base_outputs b ON b.id = cs.base_output_id
  JOIN texts t ON t.id = b.text_id
  WHERE t.split = 'dev' AND cs.reachable AND NOT cs.fragment
    AND cs.harmful_gold IS NOT NULL AND cs.probability IS NOT NULL
), pairs AS (
  SELECT CASE WHEN ok.probability > bad.probability THEN 1.0
              WHEN ok.probability = bad.probability THEN 0.5 ELSE 0 END AS win
  FROM s ok JOIN s bad ON NOT ok.harmful_gold AND bad.harmful_gold
)
SELECT (SELECT count(*) FROM s WHERE harmful_gold)     AS n_harmful,
       (SELECT count(*) FROM s WHERE NOT harmful_gold) AS n_harmless,
       round(avg(win), 3)                              AS auc,
       (SELECT count(*) FROM changed_spans WHERE fragment)             AS n_fragments,
       (SELECT count(DISTINCT text_id) FROM s2)                         AS n_texts
FROM pairs;

-- Main verdict: C5 vs C1 per seed, against the memo's three criteria.
CREATE VIEW v_c5_vs_c1 AS
WITH m AS (SELECT * FROM v_condition_metrics)
SELECT c1.seed, c1.split,
       c1.harm_per_100w AS c1_harm, c5.harm_per_100w AS c5_harm,
       c1.preservation_rate AS c1_pres, c5.preservation_rate AS c5_pres,
       round(c5.mean_fkgl_gain / NULLIF(c1.mean_fkgl_gain,0), 3) AS simplification_kept,
       (c5.harm_per_100w < c1.harm_per_100w)                    AS crit_less_harm,
       (c5.preservation_rate >= c1.preservation_rate)           AS crit_preservation,
       (c5.mean_fkgl_gain / NULLIF(c1.mean_fkgl_gain,0)
          >= (SELECT threshold FROM success_criteria WHERE key='min_simplification_kept')) AS crit_simplification,
       CASE
         WHEN c1.n_reviewed < c1.n_outputs OR c5.n_reviewed < c5.n_outputs THEN 'pending annotation'
         WHEN c5.harm_per_100w < c1.harm_per_100w
          AND c5.preservation_rate >= c1.preservation_rate
          AND c5.mean_fkgl_gain / NULLIF(c1.mean_fkgl_gain,0)
              >= (SELECT threshold FROM success_criteria WHERE key='min_simplification_kept') THEN 'success'
         WHEN c5.harm_per_100w < c1.harm_per_100w THEN 'partial: less harm, other criterion missed'
         ELSE 'negative: no harm reduction' END AS verdict,
       c1.n_reviewed AS c1_reviewed, c5.n_reviewed AS c5_reviewed, c1.n_outputs AS n_outputs
FROM m c1 JOIN m c5 ON c5.seed = c1.seed AND c5.split = c1.split
WHERE c1.condition = 'C1' AND c5.condition = 'C5';

-- Stability: same verdict on every seed of the held-out split?
CREATE VIEW v_stability AS
SELECT split,
       count(*)                          AS seeds,
       count(DISTINCT verdict)           AS distinct_verdicts,
       (count(DISTINCT verdict) = 1)     AS stable,
       min(verdict)                      AS verdict_if_stable,
       CASE WHEN min(verdict) = 'pending annotation' THEN 'pending annotation'
            WHEN count(DISTINCT verdict) = 1 AND min(verdict) <> 'negative: no harm reduction'
            THEN 'German replication allowed in thesis' ELSE 'German transfer untested' END AS german_gate
FROM v_c5_vs_c1
GROUP BY split;

-- Project feasibility: hours spent against plan.
CREATE VIEW v_progress AS
SELECT m.month, m.planned_hours,
       coalesce(sum(w.hours),0)                                   AS hours_spent,
       round(100.0 * coalesce(sum(w.hours),0) / m.planned_hours,1) AS pct_of_plan,
       m.done, m.main_output
FROM milestones m LEFT JOIN work_log w ON w.month = m.month
GROUP BY m.month, m.sort, m.planned_hours, m.done, m.main_output
ORDER BY m.sort;

-- ---------- Grammar rule flags (added for the pilot) ----------
CREATE TABLE grammar_flags (
  condition_output_id  int  NOT NULL REFERENCES condition_outputs(id) ON DELETE CASCADE,
  rule                 text NOT NULL,     -- long_sentence, passive, abbreviation
  n                    int  NOT NULL,
  example              text,
  PRIMARY KEY (condition_output_id, rule)
);
