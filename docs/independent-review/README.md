# Independent review protocol

**Status: one human review of the original cards is summarized in `HUMAN_REVIEW.md`; expert review has not been established.** This pack tests whether the supplied evidence is clear and whether a reviewer considers a range worth investigating. It does not validate fraud, caller identity, common control, blocking decisions, real-world benefit, or model accuracy.

## For the coordinator

1. Recruit a reviewer who did not develop or tune DropNet. Record relevant expertise and any relationship to the team. A non-expert can assess clarity; do not describe that as expert validation. The initial reviewer’s experience and the limits of independence are documented separately.
2. Give the reviewer only `REVIEWER.md`, `cases.md`, and a copy of `answers.csv`. Do not give them the selection key or tell them the group sizes before they finish. Counts in the cards may nevertheless reveal signals: this is single-blind with respect to labels, not full blinding.
3. Ask them to complete all 30 cases independently before discussing results. Preserve unanswered and unsure cases. Do not fill answers for the reviewer, change their responses, or tune rules against these cases before the initial evaluation is recorded. Keep a dated original. Responses may contain personal details; obtain consent before sharing.
4. Report answers separately for each selection stratum; counts and proportions use all 10 selected cases in that stratum as the denominator, including missing and unsure. A combined percentage over the deliberately balanced sample is not an estimate for all ranges. Include uncertainty, selection limitations and cases where the reviewer disagreed. There is no independent ground truth in this pack and no precision/recall claim is justified.
5. After fixes, prepare a new, separately selected holdout, avoiding these blocks and overlapping data. State any deviations from this protocol. A second independent reviewer would enable agreement analysis, but is not required to begin.

## Sampling and reproducibility

Run from the repository root with its Python environment: `python scripts/generate_independent_review.py`. The generator reads all `data/ftc/raw/*.csv.gz` through the project parser, groups reports by six-digit reported caller range, sorts candidate ranges, and samples 10 from each group using Python `random.Random(20261117)`, then shuffles the 30 cases. `manifest.json` records SHA-256 hashes and candidate counts; `selection-key.json` contains the blinded group assignments and actual eligible counts.

Groups are based on the count of distinct numbers from complaints **without a matching caller and consumer area code**: strong >=10; threshold 5–9; control 1–4. Missing consumer area codes are treated as non-matches, consistent with the existing pool rule. Groups are uniform random samples of observed ranges within each stratum, not samples of all calls or all US ranges. They have unequal population sizes and are intentionally balanced here. A threshold case is a pool according to this heuristic; its independent practical usefulness is unknown. The cards aggregate all complaints for a range, including matching ones, so card totals differ from eligible counts in the key. IDs are displayed sorted and truncated at 12, not randomly sampled. Sources and complaint categories may be incomplete or inaccurate.

Reproduction assumes the same input file bytes, parser and compatible Python runtime. Generating again overwrites the cards, key, manifest and blank answer template; it refuses to overwrite `answers.csv` if it contains reviewer input. Back up completed answers elsewhere. The dataset is public FTC Do Not Call complaint data, not verified fraud reports. Do not contact or accuse number owners based on the cards.

## Reporting template

- Reviewer count, relevant expertise, independence and dates: **pending**.
- Completed / missing cases: **pending**.
- For each stratum: yes / no / unsure / missing for evidence clarity and for further investigation: **pending**.
- Main reasons, missing information, disagreements, and representative failures: **pending**.
- Protocol deviations and limitations: **pending**.
- Follow-up changes and separate holdout evaluation: **pending**.

Do not replace “pending” with fabricated findings.

To count one reviewer's answers, run `python scripts/summarize_independent_review.py path/to/completed_answers.csv`. Missing rows and blank fields count as missing; invalid or duplicate cases are rejected. This produces descriptive counts only, not an overall population estimate.

## Expanded evidence cards

`case-cards-expanded.md` and `case-evidence.csv` add a hypothesis, all caller-ID complaint counts, example complaint links, and every linked complaint row for each original case. Generate them with `python scripts/expand_review_cases.py`. The script verifies all input hashes against the original manifest and leaves the original `cases.md` and answers unchanged. Report IDs derive from source filename and row, not FTC-assigned case IDs. Source categories are coded by the project parser; no full complaint narratives are supplied. Reported call dates are raw source fields and can be missing or inconsistent; filing dates are distinct. Examples are the first five sorted by report ID, not a representative sample.

**The completed human review used the original `cases.md`, not the expanded cards.** Do not present its findings as validation of the expanded version. To assess these additions, conduct a new review; for evaluating revised selection rules, use a separate holdout.

A separate [new-block follow-up pack](holdout/README.md) includes one set of completed responses; see its follow-up report for attribution limitations. It uses the same FTC snapshot and is not temporally independent.
