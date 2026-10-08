#!/usr/bin/env python3
"""Small, self-contained tool/dependency identities for the Host CI JSON bundle."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
from prepare_idma_export import verify as verify_idma_export

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def executable(path,version_args=('--version',)):
    path=Path(path).resolve()
    if not path.is_file() or not os.access(path,os.X_OK):raise ValueError('missing executable '+str(path))
    before=sha(path)
    run=subprocess.run([str(path),*version_args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,check=True,timeout=30)
    if sha(path)!=before:raise ValueError('tool changed while reading version')
    return dict(path=str(path),sha256=before,version=run.stdout.strip())

def tool_identity():
    launcher=shutil.which('verilator')
    if not launcher:raise ValueError('missing Verilator launcher')
    root=Path(os.environ['VERILATOR_ROOT'])
    backend=next((p for p in (root/'verilator_bin',root/'bin/verilator_bin') if p.is_file()),None)
    if backend is None:raise ValueError('missing Verilator backend')
    firtool=Path(os.environ['CHISEL_FIRTOOL_PATH'])/'firtool'
    tools=dict(verilator_launcher=executable(launcher),verilator_backend=executable(backend),firtool=executable(firtool),
               java=executable(shutil.which('java'),('-version',)),cxx=executable(shutil.which('g++')))
    if shutil.which('sbt'):
        path=Path(shutil.which('sbt')).resolve();tools['sbt_launcher']=dict(path=str(path),sha256=sha(path))
    return tools

def build_identity(build):
    build=Path(build);before=json.loads((build/'toolchain_before.json').read_text());after=tool_identity()
    if before!=after:raise ValueError('toolchain changed during production build')
    jars=json.loads((build/'compiler_jars.sha256.json').read_text())
    hardfloat=json.loads((build/'hardfloat.sha256.json').read_text())
    if not jars or not hardfloat:raise ValueError('missing actual compiler/HardFloat identity maps')
    jar_root=Path(os.environ['OFFLINE_TOOLS'])/'jars' if os.environ.get('OFFLINE_TOOLS') else build/'maven'
    for name,digest in jars.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(jar_root/name)!=digest:
            raise ValueError('actual compiler dependency changed: '+name)
    idma=json.loads((build/'idma_identity.json').read_text())
    export=Path(os.environ['IDMA_EXPORT'])
    rechecked=verify_idma_export(export,build/'idma_final_recheck')
    if rechecked!=idma:raise ValueError('iDMA export identity changed during build')
    exports=json.loads((export/'SHA256SUMS.json').read_text())
    keys={k:v for k,v in exports.items() if ('idma_backend' in k or k.endswith(('idma_pkg.sv','idma_generated.sv','compute.svh','typedef.svh','tc_clk.sv')))}
    if not keys:raise ValueError('missing pinned iDMA backend source identities')
    runtime=build/'verilator_runtime.json'
    report=dict(tools=after,compiler_jars_sha256=jars,compiler_jars_verified_after_build=True,hardfloat_source_sha256=hardfloat,
        idma_identity=idma,idma_backend_source_sha256=keys,idma_export_source_sha256=exports,
        verilator_runtime=json.loads(runtime.read_text()) if runtime.is_file() else dict(runtime_layout_repair_required=False))
    (build/'toolchain.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('before','after'));p.add_argument('output',type=Path)
    args=p.parse_args()
    if args.mode=='before':args.output.write_text(json.dumps(tool_identity(),indent=2)+'\n')
    else:build_identity(args.output)

if __name__=='__main__':main()
