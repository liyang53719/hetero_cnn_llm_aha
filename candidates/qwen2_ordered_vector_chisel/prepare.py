"""Apply this exact patch to a selected production postimage, never bare main.

Produces a small source overlay, not a complete build or an RTL artifact.
Pure stdlib; no Git/native/toolchain subprocesses or production module imports.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def apply_exact_patch(sources, patch):
    lines = patch.splitlines(keepends=True)
    results = {}
    i = 0
    while i < len(lines):
        if not lines[i].startswith('--- a/') or not lines[i+1].startswith('+++ b/'):
            raise ValueError('invalid patch file header')
        relative = lines[i][6:].strip()
        if lines[i+1][6:].strip() != relative or relative not in sources or relative in results:
            raise ValueError('unexpected or duplicate patch target')
        original = sources[relative].splitlines(keepends=True)
        output, cursor = [], 0
        i += 2
        while i < len(lines) and lines[i].startswith('@@ '):
            match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n', lines[i])
            if not match:
                raise ValueError('invalid hunk header')
            old_at, old_count, new_at, new_count = (int(match[1]), int(match[2] or 1), int(match[3]), int(match[4] or 1))
            old_start = old_at-1 if old_count else old_at
            if old_start < cursor or old_start > len(original):
                raise ValueError('overlapping or out-of-range hunk')
            output.extend(original[cursor:old_start])
            if len(output) != (new_at-1 if new_count else new_at):
                raise ValueError('new hunk position mismatch')
            cursor, removed, added = old_start, 0, 0
            i += 1
            while i < len(lines) and lines[i][0] in ' +-':
                if lines[i].startswith('--- a/'):
                    break
                kind, text = lines[i][0], lines[i][1:]
                if kind in ' -':
                    if cursor >= len(original) or original[cursor] != text:
                        raise ValueError('patch context mismatch')
                    cursor += 1
                    removed += 1
                if kind in ' +':
                    output.append(text)
                    added += 1
                i += 1
            if (removed, added) != (old_count, new_count):
                raise ValueError('hunk length mismatch')
        output.extend(original[cursor:])
        results[relative] = ''.join(output)
    if set(results) != set(sources):
        raise ValueError('patch target set mismatch')
    return results


def compose(selected_root):
    pins = json.loads((HERE/'PROFILE_PINS.json').read_text())
    patch = (HERE/'ordered_fold.patch').read_bytes()
    if digest(patch) != pins['patch_sha256']:
        raise ValueError('candidate patch pin mismatch')
    sources = {}
    for relative, pin in pins['selected_files'].items():
        data = (selected_root/relative).read_bytes()
        if digest(data) != pin['before_sha256'] or len(data) != pin['before_bytes']:
            raise ValueError('not the required selected postimage: '+relative)
        sources[relative] = data.decode()
    for relative, expected in pins['unchanged_selected_files'].items():
        if digest((selected_root/relative).read_bytes()) != expected:
            raise ValueError('unchanged selected client pin mismatch')
    result = apply_exact_patch(sources, patch.decode())
    for relative, text in result.items():
        pin = pins['selected_files'][relative]
        if digest(text.encode()) != pin['after_sha256'] or len(text.encode()) != pin['after_bytes']:
            raise ValueError('candidate postimage pin mismatch')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--selected-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = compose(args.selected_root.resolve(strict=True))
    if args.out.exists():
        raise ValueError('output must be a new directory')
    args.out.mkdir(parents=True)
    for relative, text in result.items():
        path = args.out/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    print(json.dumps({'status':'SOURCE_COMPOSE_PASS_COMPILE_TEMP','files':len(result),'enableOrderedVectorQkFold_default':False}))

if __name__ == '__main__':
    main()
