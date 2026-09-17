#!/usr/bin/env python3
"""Read an existing real-shape Qwen2 HostBlock log. Does not execute RTL."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from heteronpu.block_performance import audit


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--clock-hz', type=int, default=800000000)
    p.add_argument('--target', default='0.5')
    a = p.parse_args()
    try:
        result = audit(a.log.read_text(encoding='utf-8'), a.clock_hz, target=Fraction(a.target))
        result['input_file'] = str(a.log)
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if a.output:
            with a.output.open('x', encoding='utf-8') as f: f.write(text)
        print(text, end=''); return 0
    except (ValueError, ZeroDivisionError, OSError) as exc:
        print('COUNTER_AUDIT_REJECTED: ' + str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
