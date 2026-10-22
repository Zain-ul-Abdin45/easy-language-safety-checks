# Data plan (draft)

## Text types
Workplace procedures, safety instructions, schedules and deadlines, reporting instructions,
IT and access setup, leave and sickness rules.

## Sources (to check licence for each)
| Source | Type | Licence | Count |
|---|---|---|---|
| Public administration onboarding pages (public websites) | Public | TBD | |
| Public employee handbooks | Public | TBD | |
| Synthetic texts written for this project | Synthetic | Own | |

Rule: no real internal or personal onboarding material in this phase.

## Size and split
- Total: 50–100 texts, roughly one paragraph to one page each.
- Dev: ~20%. Held-out: ~80%, untouched until protocol is frozen.

## Per-text record
`id, source, licence, text_type, word_count, split, protected_items`

Protected items: names, dates, numbers, deadlines, conditions ("if ... then"), required actions.
Annotate these once per source text; used for automatic preservation checks.

## Storage
- `data/raw` original texts, `data/dev`, `data/heldout` as plain text or JSONL.
- Record collection date and URL for each public text.
