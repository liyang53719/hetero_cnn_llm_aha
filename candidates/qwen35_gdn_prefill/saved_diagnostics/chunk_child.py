"""One original head0/M64 chunk from saved actual Prep, without reference access."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

def need(ok,why):
    if not ok: raise ValueError(why)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def save(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temporary,path)
def main():
    plan_raw=Path(sys.argv[1]).read_bytes()
    need(digest(plan_raw)==os.environ['QWEN35_REVIEWED_PLAN_SHA256'],'reviewed plan changed')
    p=json.loads(plan_raw);run=Path(p['run_directory']);permit=run/'START.json'
    until=time.monotonic()+3
    while not permit.exists():
        need(time.monotonic()<until,'parent durable permit unavailable');time.sleep(.01)
    identity=json.loads(permit.read_text())
    need(identity['pid']==os.getpid() and identity['ppid']==os.getppid(),'exact parent permit')
    allowed_library=str(Path(p['vector_library']).resolve())
    reference_root=Path(p['reference_directory']).resolve()
    reference_paths={Path(name).resolve() for name in p['reference_paths']}
    def audit(event,args):
        if event.startswith('subprocess.') or event in ('os.system','os.posix_spawn','os.fork','os.forkpty','os.exec','os.spawn','pty.spawn') or event.startswith('socket.'):
            raise RuntimeError('no subprocess/network: '+event)
        if event=='ctypes.dlopen' and args[0] is not None:
            need(str(Path(args[0]).resolve())==allowed_library,'unselected ctypes library')
        if event=='import':
            need(args[0].split('.')[0] not in ('torch','transformers') and args[0] not in
                 ('candidates.qwen35_gdn_prefill.full_driver','candidates.qwen35_gdn_prefill.full_compare',
                  'candidates.qwen35_gdn_prefill.native.capture'),'reference/full replay import denied')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(os.fsdecode(args[0])).resolve()
            need(path not in reference_paths and reference_root not in path.parents and path!=reference_root and
                 not any(part.startswith('native_m') for part in path.parts),'reference read denied')
            flags=args[2] if len(args)>2 and isinstance(args[2],int) else 0
            if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                need(run==path or run in path.parents,'write outside fresh run denied')
    sys.addaudithook(audit)
    sys.path[:0]=[p['repository'],str(Path(p['repository'])/'src'),p['numpy_site']]
    started=time.monotonic();deadline=min(started+60,identity['work_stop_monotonic']-1)
    from candidates.qwen35_gdn_prefill.chunk import model as m
    from candidates.qwen35_gdn_prefill.chunk.vector import Vector16,IEEE_POLICY,FINITE_MUL_UF_BACKEND
    scalar=m.ep.DecayScalar(enable_softplus=True,enable_ieee_exp=True)
    vector=Vector16(p['vector_library'],exception_policy=IEEE_POLICY,arithmetic_backend=FINITE_MUL_UF_BACKEND)
    source=Path(p['saved_prep_slice']).read_bytes()
    need(len(source)==64*25600 and digest(source)==p['saved_prep_slice_sha256'],'saved Prep slice pin')
    memory=m.TypedMemory()
    job=m.ChunkJob(72,0x400000,0x800000,0x810000,0x820000,0x900000,64,
        heads=1,exp_policy=m.ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
    region=memory.allocate_output(job.input,len(source))
    # Explicit diagnostic rehydration, not a rerun of Prep or an original receipt.
    for offset in range(0,len(source),64):
        memory.begin_write(m.WriteCommand(job.input+offset,1,1))
        memory.write_data(struct.unpack_from('<32H',source,offset),True,mask=m.FULL_MASK)
        memory.acknowledge(m.WriteAck(1,False,64))
    memory.publish(job.input,(1,None,len(source)))
    for base,size in ((job.output,job.output_bytes),(job.state_out,job.state_bytes),(job.scratch,job.scratch_bytes)):
        memory.allocate_output(base,size)
    owner=m.ChunkOwner(scalar,vector,heads=1,host_batch=True,exp_policy=m.ep.EQUAL_HEADS_EXPERIMENTAL_EXP)
    driver=m.TypedChunkDriver(owner,memory,job)
    need(owner.geometry==(1,128,128) and owner.cumsum_policy==m.LEGACY_CUMSUM and owner.matmul_policy==m.LEGACY_MATMUL
         and vector.fatal_mask==28,'exact original policy/geometry')
    actual=run/'actual';actual.mkdir()
    save(actual/'summary.json',{'status':'RUNNING_ISOLATED_CHUNK_DIAGNOSTIC','full_block_acceptance':False})
    next_progress=time.monotonic();aborting=False;ticks=0
    while driver.response is None:
        now=time.monotonic()
        if now>=deadline: aborting=True
        need(now<identity['work_stop_monotonic'],'bounded component abort drain')
        driver.tick(abort=aborting)
        ticks+=1
        if now>=next_progress:
            save(actual/'progress.json',{'scope':'ISOLATED_HEAD0_M64','context':dict(owner.context),
                 'position':dict(owner.position),'ticks':ticks,'elapsed_seconds':now-started,
                 'aborting':aborting,'commands':[],'roots':{'generation':0}})
            next_progress=now+1
    need(memory.pending is None and driver.pending is None and scalar.client is None and vector.client is None,'component obligations not drained')
    report=driver.report()
    success=not aborting and driver.response.status is None and driver.response.staging_complete
    if success:
        output=driver.output.raw();state=driver.state_out.raw()
        need(len(output)==8192*2 and len(state)==128*128*4,'complete component extents')
        (actual/'output.bf16le').write_bytes(output);(actual/'state.fp32le').write_bytes(state)
    report.update(status='ISOLATED_CHUNK_COMPLETE_UNCOMPARED' if success else 'ISOLATED_CHUNK_FAILED',
       scope='REAL_SAVED_PREP_HEAD0_TOKENS0_63_DIAGNOSTIC',elapsed_seconds=time.monotonic()-started,
       input_provenance='Verified saved actual Prep first64 rows, rehydrated by diagnostic writes/ACKs; Prep not reexecuted',
       original_execution_status='UNKNOWN',full_block_acceptance=False,original_continuation=False,
       output_reference_read=False,state_oracle_available=False,terminal_count=1,
       output_elements=8192,policy=p['policy'],aborted_for_deadline=aborting)
    save(actual/'summary.json',report)
    need(success,'isolated chunk failed; no retry')
    print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds'],
                      'output_sha256':report['output_sha256'],'state_sha256':report['state_sha256']},sort_keys=True),flush=True)
if __name__=='__main__':main()
