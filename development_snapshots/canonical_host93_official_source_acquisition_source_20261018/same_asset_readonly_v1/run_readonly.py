"""Same-asset selected-source read-only requalification after preserved receipt-mode failure."""
import argparse,ast,hashlib,json,os,resource,signal,stat,sys,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
PLAN_SHA='f3362745687824b352e0014ada80ac69c55d6b5f758b3bc46d29cc5008e353bc'


def require(ok,why):
    if not ok:raise ValueError(why)


def pin(raw):return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def clean(path):
    p=Path(path).absolute();require('..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)),'safe normalized nonsymlink path');return p


def checked(path,expected):
    path=clean(path);require(path.is_file() and path.stat().st_size==expected['bytes']<=2*1024*1024,'fixed input size')
    with path.open('rb') as f:raw=f.read(expected['bytes']+1)
    require(pin(raw)==expected,'fixed input SHA');return raw


def load_gate(raw,path):
    m=types.ModuleType('fixed_acquisition_postflight_source');m.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),m.__dict__)
    tree=ast.parse(raw);lines=raw.splitlines(keepends=True)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='postflight']
    require(len(nodes)==1,'one fixed postflight')
    n=nodes[0];before=b''.join(lines[n.lineno-1:n.end_lineno]).decode()
    old="stat.S_IMODE(meta.st_mode)==0o600"
    new="stat.S_IMODE(meta.st_mode)==(0o644 if path.relative_to(root).as_posix()=='SOURCE.json' else 0o600)"
    require(before.count(old)==1,'one receipt-mode projection anchor')
    after=before.replace(old,new,1)
    require(after.count(new)==1 and after.replace(new,old,1)==before,'exact reverse projection')
    exec(compile(after,str(path)+'#specific-readonly-receipt-mode','exec',dont_inherit=True),m.__dict__)
    return m,{'original_postflight':pin(before.encode()),'readonly_postflight':pin(after.encode()),'sole_change':'allow only the exact SOURCE.json data receipt mode0644; all archive/member modes remain0600'}


def inventory(root):
    root=clean(root);rows=[];directories=[];total=0
    for parent,dirs,names in os.walk(root,followlinks=False):
        require(len(rows)+len(names)<=1024 and len(directories)+len(dirs)<=512,'finite original inventory')
        for name in dirs:
            p=Path(parent)/name;meta=p.lstat();require(stat.S_ISDIR(meta.st_mode) and not p.is_symlink(),'plain input directory')
            directories.append({'path':p.relative_to(root).as_posix(),'mode':stat.S_IMODE(meta.st_mode)})
        for name in names:
            p=Path(parent)/name;meta=p.lstat();require(stat.S_ISREG(meta.st_mode) and not p.is_symlink(),'plain input file')
            total+=meta.st_size;require(meta.st_size<=64*1024*1024 and total<=80*1024*1024,'bounded original input tree')
            h=hashlib.sha256();count=0
            with p.open('rb') as f:
                while True:
                    b=f.read(65536)
                    if not b:break
                    count+=len(b);require(count<=meta.st_size,'input grew');h.update(b)
            end=p.stat();require((meta.st_dev,meta.st_ino,meta.st_mode,meta.st_size,meta.st_mtime_ns)==(end.st_dev,end.st_ino,end.st_mode,end.st_size,end.st_mtime_ns) and count==meta.st_size,'input changed while reading')
            rows.append({'path':p.relative_to(root).as_posix(),'bytes':count,'sha256':h.hexdigest(),'mode':stat.S_IMODE(meta.st_mode),'device':meta.st_dev,'inode':meta.st_ino,'mtime_ns':meta.st_mtime_ns})
    return {'files':sorted(rows,key=lambda x:x['path']),'directories':sorted(directories,key=lambda x:x['path']),'bytes':total}


def config(gate,worker):
    raw=(HERE/'PLAN.json').read_bytes();require(hashlib.sha256(raw).hexdigest()==PLAN_SHA,'fixed readonly plan')
    p=json.loads(raw);gate=clean(gate);worker=clean(worker)
    graw=checked(gate/'run_gate.py',p['gate_source']);g,projection=load_gate(graw,gate/'run_gate.py')
    data={n:checked(worker/n,v) for n,v in p['worker_inputs'].items()}
    return p,g,projection,data


def save(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode();require(len(raw)<=512*1024,'finite report before write')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:require(f.write(raw)==len(raw),'complete report write')
    return pin(raw)


def expired(_signal,_frame):raise TimeoutError('read-only source requalification30s shared deadline')


def limits():
    allowed=os.sched_getaffinity(0);require(bool(allowed),'allowed CPU');os.sched_setaffinity(0,{min(allowed)})
    for kind,value in [(resource.RLIMIT_AS,512*1024*1024),(resource.RLIMIT_CPU,20),(resource.RLIMIT_FSIZE,512*1024),(resource.RLIMIT_CORE,0)]:resource.setrlimit(kind,(value,value))


def execute(args,entry):
    stop=entry+30
    require(signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK,[]),'inherited alarm block')
    require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'inherited timer')
    signal.signal(signal.SIGALRM,expired);require(time.monotonic()<stop,'initial deadline');signal.setitimer(signal.ITIMER_REAL,stop-time.monotonic());limits()
    p,g,projection,data=config(args.gate_source,args.worker_source)
    require(p['failed_actual_review']['manifest']['sha256']!='PENDING','preserved original failure actual review required')
    review=clean(args.failed_actual_review)
    for name,expected in [('MANIFEST.json',p['failed_actual_review']['manifest']),('SUMMARY.json',p['failed_actual_review']['summary'])]:checked(review/name,expected)
    source=clean(args.original_attempt);output=clean(args.output)
    require(output.parent.is_dir() and not output.exists(),'fresh output')
    require(not any(output.is_relative_to(x) or x.is_relative_to(output) for x in (source,HERE,clean(args.gate_source),clean(args.worker_source),review)),'disjoint new readonly evidence')
    for name,expected in p['original_evidence'].items():checked(source/name,expected)
    original_failure=json.loads((source/'FAILURE.json').read_bytes());child=json.loads((source/'acquire.json').read_bytes())
    require(original_failure['status']=='FAIL_PRESERVED_NO_RETRY' and original_failure['terminal_success'] is False,'original acquisition failure preserved')
    require(child['exit_code']==0 and child['cleanup_confirmed'] is True,'original worker exit0/cleanup')
    before=inventory(source)
    receipt=g.postflight(source/'artifacts',json.loads(data['FIXED_CORE_MEMBERS.json']),json.loads(data['SOURCE_PLAN.json']),p['worker_inputs'])
    require(receipt['received_bytes']==p['archive']['bytes'] and receipt['archive_sha256_observed']==p['archive']['sha256'],'fixed observed same archive')
    after=inventory(source);require(before==after,'all original input bytes/modes/identity unchanged')
    for name,expected in p['worker_inputs'].items():checked(clean(args.worker_source)/name,expected)
    checked(clean(args.gate_source)/'run_gate.py',p['gate_source'])
    require(time.monotonic()<stop,'postflight within30')
    output.mkdir(mode=0o700)
    inv_pin=save(output/'INPUT_INVENTORY.json',before)
    result={'status':'SAME_ASSET_SELECTED_SOURCE_EVIDENCE_PENDING_OUTER_EXIT0_AND_REVIEW','terminal_success':False,'original_acquisition_verdict':'FAIL_PRESERVED_NO_RETRY','original_failure_unchanged':True,'original_tree_unchanged':True,'specific_receipt_data_mode_observed':'0644','archive_and473_member_modes':'0600','selected_count':473,'selected_bytes':receipt['selected_bytes'],'archive':p['archive'],'projection':projection,'input_inventory':inv_pin,'failed_actual_review':p['failed_actual_review'],'network_started':False,'source_executed':False,'native_executed':False,'elapsed_seconds':time.monotonic()-entry,'acceptance_requires':'this new original outer exit0 within30 and independent same-asset content review; never upgrades prior acquisition FAIL'}
    require(inv_pin['bytes']+len(json.dumps(result).encode())+8192<=512*1024,'aggregate report margin')
    save(output/'RESULT.json',result);require(time.monotonic()<stop,'final save within same30')
    print(json.dumps(result,sort_keys=True))
    # Dedicated disposable read-only process. Timer remains armed until exit.


def main():
    entry=time.monotonic();a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--gate-source',type=Path,required=True);a.add_argument('--worker-source',type=Path,required=True)
    a.add_argument('--original-attempt',type=Path);a.add_argument('--failed-actual-review',type=Path);a.add_argument('--output',type=Path);a.add_argument('--execute-reviewed-readonly',action='store_true')
    args=a.parse_args()
    if args.execute_reviewed_readonly:
        require(all(x is not None for x in (args.original_attempt,args.failed_actual_review,args.output)),'complete explicit readonly binding')
        execute(args,entry)
    else:
        require(all(x is None for x in (args.original_attempt,args.failed_actual_review,args.output)),'source-only arguments')
        p,_,projection,_=config(args.gate_source,args.worker_source)
        print(json.dumps({'status':'SOURCE_ONLY_NO_ASSET_READ','projection':projection,'actual_review_ready':p['failed_actual_review']['manifest']['sha256']!='PENDING'},sort_keys=True))


if __name__=='__main__':
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use -I -S -B')
    main()
