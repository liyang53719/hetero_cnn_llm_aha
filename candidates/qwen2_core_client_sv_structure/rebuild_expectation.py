"""Rebuild exact reviewed ABI expectation from small published metadata only.
Never opens SV/FIRRTL, imports a compiler, runs target code, or authorizes a run.
"""
import argparse, hashlib, json
from pathlib import Path
from derive_ports import derive

def checked(path, pin):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular non-symlink metadata required')
    data = path.read_bytes()
    if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('metadata identity mismatch')
    return json.loads(data)

def rebuild(repository_root, package_root):
    root = Path(repository_root).resolve()
    package = Path(package_root)
    pins = json.loads((package / 'pins/SOURCE_PINS.json').read_text())['expectation']
    ref = pins['top_types_public_reference']
    relative = Path(ref['repo_path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe reference')
    source_path = root / relative
    if source_path.resolve() != source_path or not source_path.is_relative_to(root):
        raise ValueError('symlink or escaped reference')
    source = checked(source_path, ref)
    expectation = checked(package / 'EXPECTATION_TEMPLATE.json', pins['template'])
    expectation['top_ports'] = derive(source['review'])
    data = (json.dumps(expectation, indent=2, sort_keys=True) + '\n').encode()
    if len(data) != pins['original']['bytes'] or hashlib.sha256(data).hexdigest() != pins['original']['sha256']:
        raise ValueError('rebuilt expectation not exact')
    return data

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    if output.is_symlink() or output.exists() or output.parent.resolve() != output.parent.absolute():
        raise ValueError('fresh output under non-symlink existing parent required')
    data = rebuild(args.repository_root, Path(__file__).resolve().parent)
    with output.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'target_executed': False}))

if __name__ == '__main__':
    main()
