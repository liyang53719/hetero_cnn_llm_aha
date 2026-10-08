#!/usr/bin/env python3
"""Build unchanged Verilator hierarchy serially, reclaim completed PCH only.

No HDL, generated C++, arguments, makefiles, executable or library is edited.
The make graph determines leaf-first order. Each cleanup has before/after
retained hashes and an open-file check; source/results remain recoverable.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,time

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def graph(text):
    result={}
    for line in text.splitlines():
        match=re.match(r'^(\S+/lib\S+\.a):\s*(.*)$',line)
        if match:
            target,tail=match.groups()
            if Path(target).is_absolute() or '..' in Path(target).parts:raise ValueError('unsafe make target')
            result[target]=re.findall(r'(\S+/lib\S+\.a)',tail)
    if not result:raise ValueError('no hierarchy libraries')
    order=[];active=set();done=set()
    def visit(target):
        if target in done:return
        if target in active or target not in result:raise ValueError('cyclic or missing hierarchy dependency')
        active.add(target)
        for dep in result[target]:visit(dep)
        active.remove(target);done.add(target);order.append(target)
    for target in sorted(result):visit(target)
    return order

def clean(directory,receipt,rtl):
    if directory.is_symlink():raise ValueError('symlink object directory')
    targets=sorted(p for p in directory.glob('*.gch') if p.is_file() and not p.is_symlink())
    wanted={str(p.resolve()) for p in targets};opened=[]
    for fd in Path('/proc').glob('[0-9]*/fd/*'):
        try:
            if os.readlink(fd) in wanted:opened.append(str(fd))
        except OSError:pass
    if opened:raise ValueError('completed PCH still open: '+str(opened))
    retained=[rtl]+[p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and
        (p.suffix in ('.a','.so','.sv') or (p.name.startswith('V') and '.' not in p.name))]
    before={str(p):sha(p) for p in retained}
    removed=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in targets]
    report=dict(exact_directory=str(directory),open_fds=opened,removed=removed,retained_before=before)
    receipt.write_text(json.dumps(report,indent=2)+'\n')
    for p in targets:p.unlink()
    after={str(p):sha(p) for p in retained}
    if before!=after:raise ValueError('retained build artifact changed during cleanup')
    report.update(retained_after=after,retained_hashes_equal=True,freed_bytes=sum(x['bytes'] for x in removed))
    receipt.write_text(json.dumps(report,indent=2)+'\n')
    return report['freed_bytes']

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('build',type=Path)
    ap.add_argument('--reserve-bytes',type=int,default=1<<30,help='Hard free-space reserve; caller also budgets any concurrent reference output')
    a=ap.parse_args();out=a.build.resolve();obj=out/'obj';mk=obj/'VHostBlockTop_hier.mk';rtl=out/'generated/HostBlockTop.sv'
    if not mk.is_file() or not rtl.is_file() or obj.is_symlink():raise ValueError('missing immutable generated hierarchy')
    receipt=out/'bounded_build';receipt.mkdir(exist_ok=False)
    identity={str(p):sha(p) for p in [mk,rtl]+sorted(obj.glob('*__hierMkArgs.f'))}
    (receipt/'generated_inputs.sha256.json').write_text(json.dumps(identity,indent=2)+'\n')
    order=graph(mk.read_text());report=[]
    for index,target in enumerate(order+['VHostBlockTop'],1):
        if shutil.disk_usage(out).free<a.reserve_bytes:raise ValueError('hard disk reserve reached before '+target)
        log=receipt/f'{index:02d}.log';start=time.time()
        command=['make','-C',str(obj),'-f','VHostBlockTop_hier.mk' if target!='VHostBlockTop' else 'VHostBlockTop.mk','-j1',target]
        with log.open('w') as stream:subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True)
        directory=(obj/target).parent
        freed=clean(directory,receipt/f'{index:02d}_cleanup.json',rtl)
        report.append(dict(target=target,seconds=time.time()-start,artifact_sha256=sha(obj/target),log_sha256=sha(log),freed_pch_bytes=freed))
        (receipt/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
        print('BOUNDED_HIERARCHY_BUILT',target,'freed_pch_bytes='+str(freed),flush=True)
    if any(sha(Path(p))!=digest for p,digest in identity.items()):raise ValueError('generated build inputs changed')
    (receipt/'result.json').write_text(json.dumps(dict(status='PASS',jobs=1,generated_inputs_unchanged=True,stages=report),indent=2)+'\n')

if __name__=='__main__':main()
