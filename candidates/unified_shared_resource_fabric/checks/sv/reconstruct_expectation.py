"""Rebuild exact original declaration metadata, never parse FIR/SV or run a target.

Only pinned small inputs and the original pure type flattener are loaded. Output
must be a new file inside an existing nonsymlink directory. Not an execution GO.
"""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, os

HERE = Path(__file__).resolve().parent
EXPECTED_BYTES = 1868089
EXPECTED_SHA256 = '7ec0344b8ddfe1a2e31203b30001285dbc7d031f7e9948f0cb3d5a3ffce71813'

def require(ok, text):
    if not ok:
        raise ValueError(text)

def pinned(path, digest, limit):
    require(not path.is_symlink() and path.is_file(), 'input must be regular nonsymlink')
    require(path.stat().st_size <= limit, 'input size')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'input identity')
    return raw

def build():
    c = json.loads(pinned(HERE.parent / 'chirrtl/STRUCTURE_EXPECTATION.json',
        '5d06b11d881e4cfcf3605216a7fde9c71ab4e39dd074efddd6fee073fefcd0cc', 11000))
    template = HERE / 'STRUCTURE_TEMPLATE.json'
    # Template digest is also in PACKAGE_TRANSFORMS; final output digest binds it.
    require(not template.is_symlink() and template.is_file() and template.stat().st_size < 16000, 'template file')
    e = json.loads(template.read_bytes())
    require('selected_module_ports' not in e and 'top_ports' not in e, 'template contains expanded fields')
    code = HERE / 'derive_ports.py'
    pinned(code, '7426a3062c677e33e203be70ec4c7f98c02153b85ea5ddb5840d91488cf90274', 3000)
    spec = importlib.util.spec_from_file_location('pinned_source_type_flattener', code)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def flat(ports):
        out = {}
        for name, (direction, typ) in ports.items():
            module.flatten(module.parse_type(typ), name, direction, out)
        return out
    plain = {'clock': ['input', 'Clock'], 'reset': ['input', 'Reset']}
    product = copy.deepcopy(plain); product['io'] = ['output', c['top_io_type']]
    collection = copy.deepcopy(plain); collection['reset'] = ['input', 'UInt<1>']
    collection['port'] = ['output', c['top_io_type']]
    selected = {c['product']: flat(product)}
    for inst, child in c['collection_instances'].items():
        if inst == 'top':
            continue
        fields = [('flip ' if row['direction'] == 'input' else '') + name[3:] + ' : UInt<' + str(row['width']) + '>'
                  for name, row in c['fma_abi'][child].items()]
        typ = '{ ' + ', '.join(fields) + ' }'
        collection[inst + 'Port'] = ['output', typ]
        selected[child] = flat({'io': ['output', typ]})
    selected[c['top']] = flat(collection)
    vector = copy.deepcopy(plain); vector['io'] = ['output', c['vector_io_type']]
    selected[e['vector']] = flat(vector)
    e['selected_module_ports'] = selected; e['top_ports'] = selected[c['top']]
    require(len(selected) == 7 and len(selected[c['product']]) == 4599 and len(e['top_ports']) == 4618, 'strict ABI counts')
    raw = (json.dumps(e, indent=2, sort_keys=True) + '\n').encode()
    require(len(raw) == EXPECTED_BYTES and hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256, 'exact original expectation')
    return raw

def write_new(output, raw):
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'output already exists')
    require(output.parent.is_dir(), 'output parent missing')
    require(all(not p.is_symlink() for p in [output.parent, *output.parent.parents]), 'symlink output parent')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = build(); write_new(args.output, raw)
    print(json.dumps({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'scope': 'exact source-derived declaration metadata only'}))
