#!/usr/bin/env python3
"""Read-only audit of scalar ABI declarations in CIRCT output. No SV rewriting."""
from pathlib import Path
import argparse, json, re


def parse_ports(text: str, root: str) -> dict[str, tuple[str, int]]:
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    found = re.findall(r'\bmodule\s+' + re.escape(root) + r'\s*\((.*?)\);', text, re.S)
    if len(found) != 1:
        raise ValueError(f'{root}: expected one unparameterized scalar ABI, found {len(found)}')
    result = {}
    direction = None
    width = 1
    for item in found[0].split(','):
        item = item.strip()
        m = re.match(r'(input|output|inout)\b\s*(.*)', item, re.S)
        if m:
            direction, item = m.groups()
            width = 1
        item = re.sub(r'\b(wire|logic|reg|signed|unsigned)\b', ' ', item).strip()
        m = re.match(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*(.*)', item, re.S)
        if m:
            high, low, item = m.groups()
            width = abs(int(high) - int(low)) + 1
        if direction is None or not re.fullmatch(r'[A-Za-z_]\w*', item):
            raise ValueError(f'{root}: unsupported declaration {item!r}')
        if item in result:
            raise ValueError(f'{root}: duplicate port {item}')
        result[item] = (direction, width)
    return result


def expected_ports(entries: list[dict]) -> dict[str, tuple[str, int]]:
    result = {'clk_i': ('input', 1), 'rst_ni': ('input', 1)}
    for entry in entries:
        t = entry['type']
        if t == 'Bool()':
            width = 1
        elif t == 'UInt(addressBits.W)':
            width = 15
        elif t == 'UInt((2*addressBits).W)':
            width = 30
        else:
            m = re.fullmatch(r'UInt\((\d+)\.W\)', t)
            if not m:
                raise ValueError(f'unsupported type {t}')
            width = int(m[1])
        result[entry['name']] = (entry['direction'].lower(), width)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'abi_ports.json').read_text())
    files = sorted(args.directory.glob('*.sv'))
    if not files:
        raise ValueError('No emitted SV; this is not an emission test')
    text = '\n'.join(p.read_text() for p in files)
    results = []
    for name, entries in manifest.items():
        expected = expected_ports(entries)
        actual = parse_ports(text, name)
        if expected != actual:
            raise ValueError(f'{name}: missing={set(expected)-set(actual)} extra={set(actual)-set(expected)} mismatch=' +
                             repr({k:(expected[k],actual[k]) for k in expected.keys() & actual.keys() if expected[k] != actual[k]}))
        results.append({'root': name, 'checked_ports': len(actual)})
    result = {'status': 'PASS_SCALAR_ABI', 'roots': results, 'address_bits': 15,
              'scope': 'generated declaration names/directions/widths only; not functional equivalence'}
    (args.directory/'ABI_CHECK.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
