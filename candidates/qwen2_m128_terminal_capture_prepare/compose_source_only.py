"""Stdlib exact text-source composer. Never imports target or binds runtime paths."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sections(raw):
    result = {}
    current = None
    for line in raw.decode('utf-8').splitlines(keepends=True):
        if line.startswith('diff --git '):
            match = re.fullmatch(r'diff --git a/(\S+) b/(\S+)\n', line)
            need(match is not None and match[1] == match[2], 'invalid patch path')
            current = match[1]
            need(not Path(current).is_absolute() and '..' not in Path(current).parts,
                 'non-relative patch path')
            need(current not in result, 'duplicate patch section')
            result[current] = []
        else:
            need(current is not None, 'patch data before section')
            result[current].append(line)
    return result


def apply_hunks(before, lines):
    source = before.decode('utf-8').splitlines(keepends=True)
    output = []
    cursor = 0
    index = 0
    hunks = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(('new file mode ', '--- ', '+++ ')):
            need(hunks == 0, 'unexpected header after hunk')
            index += 1
            continue
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*\n', line)
        need(match is not None, 'invalid hunk header')
        old_start, old_count, new_start, new_count = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
        start = old_start - 1 if old_count else old_start
        need(cursor <= start <= len(source), 'overlapping/out-of-range hunk')
        output.extend(source[cursor:start]); cursor = start
        need(len(output) == (new_start - 1 if new_count else new_start), 'new hunk offset mismatch')
        index += 1; consumed = 0; emitted = 0
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]; index += 1
            need(line[:1] in (' ', '-', '+'), 'unsupported hunk content')
            if line[0] in (' ', '-'):
                need(cursor < len(source) and source[cursor] == line[1:], 'exact base hunk mismatch')
                cursor += 1; consumed += 1
            if line[0] in (' ', '+'):
                output.append(line[1:]); emitted += 1
        need((consumed, emitted) == (old_count, new_count), 'hunk length mismatch')
        hunks += 1
    need(hunks > 0, 'empty source delta')
    output.extend(source[cursor:])
    return ''.join(output).encode('utf-8')


def build(source_root):
    """Validate external exact old composed postimages, return eight source bytes."""
    pins = json.loads((HERE / 'COMPOSITION_PINS.json').read_text())
    delta = (HERE / 'SOURCE_ONLY.patch').read_bytes()
    need(identity(delta) == pins['patch'], 'public source patch changed')
    parts = sections(delta)
    need(set(parts) == set(pins['files']), 'patch file set differs')
    built = {}
    for rel, pin in pins['files'].items():
        source = source_root / rel
        if pin['base'] is None:
            need(not source.exists(), 'new source already present: ' + rel)
            before = b''
        else:
            before = source.read_bytes()
            need(identity(before) == pin['base'], 'not exact old composed postimage: ' + rel)
        after = apply_hunks(before, parts[rel])
        need(identity(after) == pin['postimage'], 'reconstructed source differs: ' + rel)
        need(after == (HERE / 'postimage' / rel).read_bytes(), 'published postimage differs: ' + rel)
        built[rel] = after
    return built


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True,
                        help='Exact prior composed candidate source root, NOT raw main')
    parser.add_argument('--output-root', type=Path, required=True,
                        help='New empty destination; only eight source postimages, not a runtime')
    args = parser.parse_args()
    need(not args.output_root.exists(), 'output must not exist')
    built = build(args.source_root.resolve(strict=True))
    args.output_root.mkdir(parents=True, exist_ok=False)
    for rel, raw in built.items():
        path = args.output_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    print(json.dumps({'source_postimages': len(built), 'runtime_bound': False,
                      'execution_ready': False, 'private_source_pins_created': False}, sort_keys=True))


if __name__ == '__main__':
    main()
