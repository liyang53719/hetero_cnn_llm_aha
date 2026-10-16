"""Opt-in tiny native-model checks; never imported by default cold discovery."""
import ctypes as C,hashlib,importlib.util,json,sys,time
from pathlib import Path
from . import prepare
from ..attention_matrix_batch.test_model import ref_fma

def require(ok):
    if not ok:raise ValueError('native packed profile check')
def load_service(root):
    p=Path(root)/prepare.TARGETS[1]
    spec=importlib.util.spec_from_file_location('packed_matrix_service_under_test',p)
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m

def run(root,library):
    before=prepare.snapshot();pins=prepare.check();root=Path(root);library=Path(library)
    for n in prepare.TARGETS:require(prepare.digest(root/n)==pins['generated'][n])
    m=load_service(root);lib=m.configure_library(C.CDLL(str(library.resolve())))
    owner=object();checks=[]
    def fresh():
        require(lib.td_reset()==0);s=m.MatrixService(lib);require(s.acquire(owner,'normal',17));return s
    def complete(s):
        result=s.result;require(result is not None)
        require(s.ports()['result'] is result and s.done is None)
        for action in (lambda:s.retire_owner_response(owner),lambda:s.release(owner)):
            try:action()
            except m.MatrixProtocolError:pass
            else:raise ValueError('premature owner retirement accepted')
        values=tuple(result.value[r][c] for r in range(16) for c in range(256))
        require(not s.accept_step(owner,m.NormalStep(0,(0,)*16,(0,)*256,True,True,finish=True)))
        s.retire_result(owner,result);done=s.done;require(done is not None and s.done is done);s.retire_done(owner,done)
        s.retire_owner_response(owner);s.release(owner);return values
    def group(opcode,steps,mask,profile,packets,columns):
        s=fresh();address=s.resource_address;require(s.accept_group(owner,m.NormalGroup(opcode,steps,3,mask,profile)))
        expected=[0]*4096
        for i,(a,b) in enumerate(packets):
            last=i==steps-1;require(s.accept_step(owner,m.NormalStep(i,a,b,i==0,last,finish=last,emit=last)))
            require(s.resource_address==address)
            if not last:require(s.result is None and s.done is None)
            for r in range(16):
                for c in range(columns):expected[r*256+c]=ref_fma(a[r]<<16,b[c]<<16,expected[r*256+c])
        result=complete(s);require(result==tuple(expected));require(lib.matrix_normal_fmas()==steps*16*columns)
        checks.append(dict(case='qk' if opcode==0x23 else 'pv',profile=profile,steps=steps,fmas=lib.matrix_normal_fmas(),output_sha256=hashlib.sha256(b''.join(x.to_bytes(4,'little') for x in result)).hexdigest()))
    palette=(0x3f80,0xbf80,0x3e80,0xbe80,0x0001,0x8000)
    packets=tuple((tuple(palette[(r+i)%len(palette)] for r in range(16)),tuple(palette[(c+2*i)%len(palette)] for c in range(256))) for i in range(8))
    group(0x23,8,255,2,packets,256)
    group(0x24,3,15,2,packets[:3],128)
    s=fresh();require(s.accept_group(owner,m.NormalGroup(0x24,128,9,15,2)))
    for i in range(128):
        last=i==127
        require(s.accept_step(owner,m.NormalStep(i,(0x3f80,)*16,(0x3f80,)*256,i==0,last,finish=last,emit=last)))
        if not last:require(s.result is None)
    value=complete(s);require(all(value[r*256+c]==(0x43000000 if c<128 else 0) for r in range(16) for c in range(256)))
    require(lib.matrix_normal_fmas()==128*2048)
    checks.append(dict(case='pv128_boundary',profile=2,steps=128,fmas=128*2048))
    # Existing profile1 still emits only last, using all enabled slice0 cells.
    group(0x24,3,255,1,packets[:3],256)
    # Default0 remains its original per-step reply contract.
    s=fresh();require(s.accept_group(owner,m.NormalGroup(0x23,8,4)))
    for i,(a,b) in enumerate(packets):
        last=i==7;require(s.accept_step(owner,m.NormalStep(i,a,b,i==0,last,finish=last,emit=True)))
        r=s.result;require(r is not None);s.retire_result(owner,r)
        if last:s.retire_done(owner,s.done)
        require(lib.matrix_legacy_reply_retire(lib.matrix_ticket())==0)
    s.retire_owner_response(owner);s.release(owner);require(lib.matrix_normal_fmas()==4096)
    checks.append(dict(case='legacy_default',steps=8,fmas=4096))
    # Nonselected enabled-cell NaN is returned, not turned into protocol poison.
    for selected in (False,True):
        s=fresh();require(s.accept_group(owner,m.NormalGroup(0x24,1,5,15,2)))
        a=[0x3f80]*16;a[0 if selected else 15]=0x7fc1
        require(s.accept_step(owner,m.NormalStep(0,tuple(a),(0x3f80,)*256,True,True,finish=True,emit=True)))
        require(not s.reset_required and not s.result.error)
        values=complete(s)
        require((values[(0 if selected else 15)*256]&0x7f800000)==0x7f800000)
        if not selected:require(values[0]==0x3f800000)
        checks.append(dict(case='selected_nonfinite' if selected else 'nonselected_nonfinite',protocol_error=False,selected_fault_timing_qualified=False))
    # Malformed profile shape faults; no silent fall-through to another mode.
    for opcode,steps,mask in ((0x23,7,255),(0x23,8,1),(0x24,0,15),(0x24,129,15),(0x24,1,255)):
        s=fresh();require(s.accept_group(owner,m.NormalGroup(opcode,steps,7,mask,2)));require(s.reset_required)
    for context,clear,last,finish,emit in ((1,True,False,False,False),(0,False,False,False,False),(0,True,False,False,True),(0,True,True,True,True)):
        s=fresh();require(s.accept_group(owner,m.NormalGroup(0x23,8,8,255,2)))
        require(s.accept_step(owner,m.NormalStep(0,(0x3f80,)*16,(0x3f80,)*256,clear,last,context=context,finish=finish,emit=emit)))
        require(s.reset_required and lib.matrix_normal_fmas()==0)
    prepare.check();require(prepare.snapshot()==before)
    return dict(status='PASS_TINY_PACKED_NATIVE_MODEL',source_sha256=before,generated_sha256=pins['generated'],library_sha256=prepare.digest(library),checks=checks,
      full_public_admission=False,selected_fault_timing_qualified=False,rtl_execution=False,independent_goldens_changed=False)
if __name__=='__main__':
    start=time.monotonic();r=run(sys.argv[1],sys.argv[2]);r['elapsed_seconds']=time.monotonic()-start
    Path(sys.argv[3]).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(dict(status=r['status'],elapsed_seconds=r['elapsed_seconds'])))
