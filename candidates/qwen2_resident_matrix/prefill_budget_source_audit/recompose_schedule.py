#!/usr/bin/env python3
"""Optional source-only reconstruction; no schedule, numerical or RTL execution."""
import argparse, hashlib, importlib, json, sys, tempfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate-repo-root',required=True,type=Path)
    args=parser.parse_args()
    root=args.candidate_repo_root.resolve()
    receipt=json.loads((Path(__file__).parent/'evidence_sources/PACKED_COMPOSITION_RECEIPT.json').read_text())
    expected=dict(receipt['sources'],**receipt['own'])
    failures=[name for name,digest in expected.items() if not (root/name).is_file() or
              hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest]
    if failures:
        raise ValueError('composition input mismatch: '+', '.join(failures))
    sys.path.insert(0,str(root))
    prepare=importlib.import_module('candidates.qwen2_resident_matrix.attention_packed_m128.prepare')
    with tempfile.TemporaryDirectory(prefix='budget-source-only-') as temp:
        out=prepare.compose(Path(temp)/'composed')
        digest=hashlib.sha256((out/receipt['generated_path']).read_bytes()).hexdigest()
        if digest!=receipt['generated_sha256']:
            raise ValueError('generated schedule identity mismatch')
    print(json.dumps({'source_only_composition':True,'numerical_execution':False,
                      'rtl_execution':False,'generated_sha256':digest},indent=2))

if __name__=='__main__':main()
