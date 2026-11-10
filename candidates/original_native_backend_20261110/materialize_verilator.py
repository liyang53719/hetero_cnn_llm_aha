"""Exact existing Verilator package, job-local extraction only; no sudo/install scripts."""
import argparse,hashlib,json,pathlib,subprocess,urllib.request
D=pathlib.Path(__file__).parent
SHA='238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2'
URL='https://deb.debian.org/debian/pool/main/v/verilator/verilator_5.032-1+b2_amd64.deb'
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(out,execute):
 if not execute:raise ValueError('explicit acquisition required')
 if out.exists():raise ValueError('fresh root required')
 out.mkdir();deb=out/'verilator.deb'
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*a,**k):raise ValueError('unreviewed redirect')
 with urllib.request.build_opener(NoRedirect()).open(URL,timeout=30) as response,deb.open('xb') as target:
  total=0
  while True:
   data=response.read(1<<20)
   if not data:break
   total+=len(data)
   if total>7565144:raise ValueError('package cap')
   target.write(data)
 if deb.stat().st_size!=7565144 or digest(deb)!=SHA:raise ValueError('package identity')
 package=out/'verilator-package';subprocess.run(['/usr/bin/dpkg-deb','--extract',str(deb),str(package)],check=True,timeout=30)
 m=json.loads((D/'VERILATOR_MANIFEST.json').read_text())
 for x in m['files']:
  if not x['path'].startswith(('usr/bin/','usr/share/verilator/')):continue
  p=package/x['path']
  if not p.is_file() or p.stat().st_size!=x['bytes'] or digest(p)!=x['sha256']:raise ValueError('tool closure '+x['path'])
 wrapper=out/'verilator';wrapper.write_text('#!/bin/sh\nset -eu\nROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport VERILATOR_ROOT="$ROOT/verilator-package/usr/share/verilator"\nexport VERILATOR_BIN="$ROOT/verilator-package/usr/bin/verilator_bin"\nexec "$ROOT/verilator-package/usr/bin/verilator" "$@"\n');wrapper.chmod(0o700)
 (out/'SOURCE_RECEIPT.json').write_text(json.dumps({'scope':'TOOL_BYTES_ONLY_PENDING_ACTUAL_FRONTEND','package_sha256':SHA,'wrapper_sha256':digest(wrapper),'verified_operational_files':sum(x['path'].startswith(('usr/bin/','usr/share/verilator/')) for x in m['files']),'excluded_nonoperational':'usr/share/doc and man links are distribution documentation, not executable/header closure'},indent=2)+'\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--output',type=pathlib.Path,required=True);a.add_argument('--execute-reviewed-acquisition',action='store_true');v=a.parse_args();run(v.output,v.execute_reviewed_acquisition)
