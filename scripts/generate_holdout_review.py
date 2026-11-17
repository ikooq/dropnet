"""Create new-block review cases from the original snapshot (not a temporal holdout)."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'docs' / 'independent-review'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    original = json.loads((PACK / 'selection-key.json').read_text(encoding='utf-8'))['selection']
    holdout = PACK / 'holdout'
    generator = module('review_generate', 'generate_independent_review.py')
    generator.OUT = holdout
    generator.SEED = 20261118
    generator.EXCLUDED_BLOCKS = {item['block'] for item in original}
    generator.generate()
    selected = json.loads((holdout / 'selection-key.json').read_text(encoding='utf-8'))['selection']
    if generator.EXCLUDED_BLOCKS & {item['block'] for item in selected}:
        raise SystemExit('Holdout overlaps an original block')
    expander = module('review_expand', 'expand_review_cases.py')
    expander.PACK = holdout
    expander.main()
    print('Verified holdout has no original block overlap')


if __name__ == '__main__':
    main()
