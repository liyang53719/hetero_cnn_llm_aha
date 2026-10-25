"""Assemble pinned source bytes only. Never import/execute assembled target code."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json

def relative_name(value):
    if not isinstance(value, str) or not value:
        raise ValueError('empty or non-string relative path')
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(x in ('', '.', '..') for x in p.parts) or '\\' in value:
        raise ValueError('unsafe relative path')
    return p

def assemble(repo_root, output, manifest):
    root = Path(repo_root).resolve(strict=True)
    out = Path(output)
    if not root.is_dir() or out.exists() or out.is_symlink():
        raise ValueError('repository must exist; output must be fresh')
    if manifest.get('schema') != 'source-only-byte-assembly-v1' or not isinstance(manifest.get('files'), list) or not manifest['files']:
        raise ValueError('invalid source manifest')
    pending = []
    targets = set()
    for row in manifest['files']:
        source = relative_name(row['repo_path'])
        target = relative_name(row['target'])
        if str(target) in targets:
            raise ValueError('duplicate assembly target')
        targets.add(str(target))
        src = root.joinpath(*source.parts)
        cursor = root
        for part in source.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError('source symlink denied')
        if not src.is_file() or not src.resolve(strict=True).is_relative_to(root):
            raise ValueError('source outside repository or missing')
        data = src.read_bytes()
        if type(row['bytes']) is not int or row['bytes'] < 0 or len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('source identity mismatch: ' + str(source))
        pending.append((target, data))
    # Complete every source check before creating output. Already-read bytes are used.
    out.mkdir(parents=False, exist_ok=False)
    for target, data in pending:
        dest = out.joinpath(*target.parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as handle:
            handle.write(data)
    return {'files': len(pending), 'bytes': sum(len(data) for _, data in pending), 'target_executed': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', choices=('r2', 'r3'), default='r3')
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).resolve().parent / ('pins/' + args.revision.upper() + '_ASSEMBLY_MANIFEST.json')).read_text())
    print(json.dumps(assemble(args.repo_root, args.output, manifest), sort_keys=True))

if __name__ == '__main__':
    main()
