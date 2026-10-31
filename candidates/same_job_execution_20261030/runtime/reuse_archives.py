"""Original53 archive audit only: zero download/link/extraction or historical PASS."""
import argparse,json,pathlib
import runtime_reuse as r
P=pathlib.Path

def run(binding,digest):
 b=r.read(dict(path=str(binding),bytes=P(binding).stat().st_size,sha256=digest));r.admit(b)
 for p,h in b['pins'].items():r.need(r.sha(p)==h,'archive reuse source pin')
 m,_=r.manifest(b);rows=r.original_archives(b,m)
 out=P(b['output']);r.need(out.is_absolute()and out.is_relative_to(P(b['job_root']))and not out.exists()and all(not p.is_symlink()for p in(out,*out.parents)),'fresh archive audit output')
 r.need(all(not out.is_relative_to(P(e['import_root']))for e in m['entries'].values())and all(not out.is_relative_to(P(v['path']).parent)for v in rows),'archive audit never writes historical inputs')
 out.mkdir();r.save(out/'ARCHIVES.json',dict(scope='READ_EXISTING_PINNED_ARCHIVES_NO_INSTALL',identity=b['identity'],runtime_reuse_manifest=b['runtime_reuse_manifest'],archives=rows,network_body_bytes=0,logical_fetches=0,reference_qualified=False,numerical_qualified=False))
 for p,h in b['pins'].items():r.need(r.sha(p)==h,'post archive reuse source pin')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--binding',type=P,required=True);p.add_argument('--binding-sha256',required=True);a=p.parse_args();run(a.binding,a.binding_sha256)
