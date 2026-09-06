#!/usr/bin/env python3
"""Verify a pinned public iDMA export and generate a relocated filelist only."""
import argparse,hashlib,json
from pathlib import Path

PIN='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'
def verify(root:Path,out:Path)->dict:
    root=root.resolve();out.mkdir(parents=True,exist_ok=True)
    commits=json.loads((root/'COMMITS.json').read_text())
    if commits.get('idma')!=PIN:raise ValueError('iDMA revision drift')
    manifest=json.loads((root/'SHA256SUMS.json').read_text())
    if not manifest:raise ValueError('empty iDMA identity')
    for name,digest in manifest.items():
        p=(root/name).resolve()
        if not p.is_relative_to(root) or not p.is_file():raise ValueError('unsafe/missing source '+name)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('source drift '+name)
    text=(root/'idma.f.in').read_text().replace('@ROOT@',str(root))
    if '@ROOT@' in text:raise ValueError('unresolved filelist root')
    # The generated Bender ASIC list does not include the generic ICG; the
    # retained-source list adds its separately pinned definition exactly once.
    report={'commits':commits,'files_verified':len(manifest),'export_manifest_sha256':hashlib.sha256((root/'SHA256SUMS.json').read_bytes()).hexdigest()}
    (out/'idma.f').write_text(text);(out/'idma_identity.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('export',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    try:print(json.dumps(verify(a.export,a.output)))
    except (ValueError,OSError,KeyError) as e:raise SystemExit('PINNED_IDMA_SOURCE_FAILED: '+str(e))
