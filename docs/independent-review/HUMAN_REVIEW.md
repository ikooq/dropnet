# Human review of the initial 30 cases

> **Not counted as evidence.** All 30 answers, including confidence scores, are identical to an earlier AI answer file, so this round cannot be treated as an independent human review. It is kept only as a record. The label-blinded review is in [`../validation-study/EXPERT_REVIEW.md`](../validation-study/EXPERT_REVIEW.md).

One reviewer completed all 30 original `cases.md` cards. I was told the reviewer did not see the earlier AI answers; the reviewer described basic experience in data analysis and information assessment and consented to publication of their answers. Specialized telecom or investigative expertise was not claimed. The submitted file retains the identifier `AI-R01` and the phrase `AI-assisted`; their origin and whether the reviewer saw the selection key are unconfirmed. All 30 decisions and confidence scores match an earlier AI answer file; reasons are worded differently. These facts limit what can be concluded about review independence. No personal identity is published here.

| Sample stratum | Clarity yes / no / unsure | Investigate yes / no / unsure |
|---|---|---|
| Strong signal (10) | 10 / 0 / 0 | 10 / 0 / 0 |
| Threshold (10) | 10 / 0 / 0 | 4 / 0 / 6 |
| Control (10) | 10 / 0 / 0 | 1 / 4 / 5 |
| Total (30) | 30 / 0 / 0 | 15 / 4 / 11 |

There were no missing answers to these two questions. Confidence was 3/5 for 18 cases, 4/5 for 10 and 5/5 for two. The strata were deliberately balanced, not sampled in proportion to the population, so the overall 15/30 is not a population estimate. These are reviewer judgments about clarity and whether to investigate; they are not labels of fraud or measured predictive accuracy.

C09 is a useful counterexample: the reviewer considered six reports involving two IDs worth examining despite the control stratum; three reports used the impersonation subject category. This does not establish a common operator or wrongdoing. The reviewer expressed uncertainty on six threshold cases and five control cases, often citing generic subject categories or insufficient detail. C24, three complaints about one ID filed on one day, was judged insufficient for range-wide investigation; duplicate reports were a possible alternative, not an established fact. The review did not provide ground truth by which to declare algorithm errors.

Frequently requested missing evidence included complaint narratives, call timestamps, independent complainant counts, per-number counts, and verified origin. It has not been established that all these fields exist in the public source. The later `case-cards-expanded.md` and `case-evidence.csv` make per-number counts and report-to-number links explicit and separate filing from reported call dates. Those expanded cards were created **after** the review; these results do not validate them.

The sample selection, source hashes and limits are described in `README.md` and `manifest.json`. A human review by one person is preliminary, not an expert fraud assessment or production evaluation. A separate holdout and further review are needed to assess changes; review of different blocks from the same FTC snapshot is not temporal or dataset independence.
