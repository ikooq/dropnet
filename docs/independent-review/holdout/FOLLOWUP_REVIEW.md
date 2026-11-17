# Follow-up review of 30 new-block cases

The response file contains 30 completed cases under one identifier. The user reports that the reviewer made the judgments personally, with AI used to shorten the text, and agreed to publication of anonymized results. The reported area of expertise is consumer-complaint data and pattern analysis, but professional qualifications have not been verified. According to the user, the reviewer was not given and did not use the group selection key, but previous ratings were available in the conversation; the review therefore cannot be considered fully blinded or independent of prior responses. No personal identity or raw answers are published in this report.

| Sample stratum | Evidence clear: yes / no / unsure | Investigate: yes / no / unsure |
|---|---|---|
| Strong signal (10) | 10 / 0 / 0 | 8 / 0 / 2 |
| Threshold (10) | 10 / 0 / 0 | 3 / 0 / 7 |
| Control (10) | 10 / 0 / 0 | 0 / 4 / 6 |
| Total (30) | 30 / 0 / 0 | 11 / 4 / 15 |

There are no missing values for these questions. Confidence scores: 2/5 for three cases, 3/5 for 21, 4/5 for five, and 5/5 for one. These groups were deliberately balanced, so the totals do not estimate population rates. Judgments are about clarity and whether to investigate, not verified fraud labels.

The reviewer noted inconsistent chronology. In C10, report `1c1408756a9d` has filing date 2026-10-15 and reported call date 2026-10-16; in C30, report `1187bdeb54d6` has filing date 2026-10-20 and reported call date 2026-10-21. Both were checked against `case-evidence.csv`. The causes are unknown and the original values must not be silently corrected. C22 has 97 complaints, with 45 reported call dates on October 9 and 16 on October 8, 2026; those figures do not establish a common caller. In C08, the reviewer considered repeated-number and complaint-category evidence worth follow-up. Multiple cases with broad or mixed subjects received an unsure rating. Requested evidence often included call content and independently verified origin; availability of those fields is not established.

This is a new-block sample drawn from the same historical FTC snapshot as the initial review, not a new dataset or temporal holdout. Cards included hypotheses, potentially influencing responses. Both cards and cases changed, so comparisons with the initial review cannot isolate the effect of UI changes. The new repeated-number UI was not independently assessed by this card review. FTC complaints and caller IDs are unverified; there is no independent ground truth here to estimate fraud-detection accuracy or recall.

Potential next work: visibly flag reported call dates later than filing dates without changing source values, make generic subject categories more visible, and separately evaluate the UI using fresh data and a documented protocol.
