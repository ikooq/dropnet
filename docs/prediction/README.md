# Pre-registered forward test

On 2026-11-23 Dropnet's rule was run on every FTC Do Not Call file published up to that day and its output was frozen
here, before any of the complaints it will be judged on existed. The git commit that adds this folder (and its copy on
GitHub) is the timestamp; `manifest.json` holds SHA-256 hashes of the frozen lists and of every training file, and
`check` refuses to run if a list has changed.

## What is frozen

Training: 29 daily files, 2026-10-12 to 2026-11-19, 350,525 complaints filed up to 2026-11-18.

| File | Content |
|---|---|
| `ranges.txt` | 7,461 ranges (5,765 geographic, the rest toll-free): six-digit prefixes with at least 5 different reported numbers, counting only reports whose caller area code differs from the consumer's |
| `numbers.txt` | 23,740 numbers reported at least twice: the blocklist baseline |
| `seen_numbers.txt.gz` | all 292,956 numbers seen in training, to count complaints about numbers never seen before |

## Test set, fixed in advance

Every FTC daily file published after 2026-11-19 and available on **2026-12-08**, and in it every complaint filed after
2026-11-18. A second count keeps only complaints whose call date is also after 2026-11-18 and not after the filing date.
Nothing is learned from the test files; the lists above are used as they are.

## Hypotheses, stated before the data exist

1. Numbers + geographic ranges match **at least 2×** the complaints that numbers alone match.
2. The same holds on the call-date subset.
3. Of complaints about numbers never seen in training, **at least 10%** fall in a frozen geographic range.

The result is published whatever it is, including if a hypothesis fails.

## Check

```bash
python -c "from pathlib import Path; from dropnet.ftc.fetch import fetch; fetch(Path('data/ftc/after-freeze'), days=20)"
python scripts/preregister.py check --prediction docs/prediction --test-dir data/ftc/after-freeze
```

`check` uses only files dated after the last training file, whatever else is in the folder.

## Dry run of the check on past data

To test the procedure itself, the same two commands were run with a freeze on `data/ftc/raw` only (files to
2026-11-13) and the four later files as the test set: numbers alone matched 5.8% of 54,252 complaints, numbers +
geographic ranges 19.2% (3.3×); on the call-date subset 4.3% → 16.7% (3.9×); 14.2% of complaints about never-seen
numbers were in a frozen geographic range. Those files are now training data, so this run is not part of the test.
