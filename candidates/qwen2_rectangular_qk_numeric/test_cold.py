"""Cold checks only: frozen fixture bits, source wiring and runner receipts.

No Scala, RTL, network or CI execution. C++ syntax uses a declared-port stub;
that check cannot establish the actual generated ABI or numerical execution.
"""
import ctypes as C
import ctypes.util
import json
import os
import signal
import time
from pathlib import Path
import re
import subprocess

import pytest

from candidates.qwen2_exact_tree_scheduler import arithmetic as exact
from candidates.qwen2_rectangular_qk_payload.model import configure

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

@pytest.fixture(scope='module')
def native(tmp_path_factory):
    out=tmp_path_factory.mktemp('qk-numeric-cold')/'kernel.so'
    subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC','-fno-fast-math',
        '-ffp-contract=off','-frounding-math','-fno-tree-vectorize',
        str(ROOT/'candidates/qwen2_rectangular_qk_payload/kernel.cpp'),'-o',str(out)],
        check=True,capture_output=True,timeout=30)
    return configure(C.CDLL(str(out)))


def words():
    return [int(x,16) for x in re.findall(r'0x([0-9a-f]{8})u',(HERE/'expected_tail.hpp').read_text())]


def test_680_frozen_intermediate_words_equal_integer_fma_and_native_libm(native):
    class Wire(C.c_float):pass
    lib=C.CDLL(ctypes.util.find_library('m') or 'libm.so.6')
    lib.fmaf.argtypes=[C.c_float]*3;lib.fmaf.restype=Wire
    def wire(bits):return Wire.from_buffer_copy(bits.to_bytes(4,'little'))
    acc=[[0]*17 for _ in range(5)];got=[]
    for t in range(8):
        for ctx in range(5):
            j=ctx+16*t;a=(0x3f00+j%7)<<16
            for key in range(17):
                b=(0x3e80+(key+j)%9)<<16
                x=exact.fma(a,b,acc[ctx][key])
                y=lib.fmaf(wire(a),wire(b),wire(acc[ctx][key]))
                assert x==int.from_bytes(C.string_at(C.byref(y),4),'little')
                acc[ctx][key]=x
            got.extend(acc[ctx])
    assert len(got)==680 and got==words()


def test_frozen_native_final_partials_match_tail_and_signed_zero(native):
    out=(C.c_uint32*4096)();valid=(C.c_uint32*16)(17,*([0]*15))
    assert native.reset()==0 and native.begin(5)==0
    for t in range(8):
        for ctx in range(5):
            j=ctx+16*t
            a=(C.c_uint16*16)(0x3f00+j%7,*([0]*15))
            b=(C.c_uint16*256)(*([0x3e80+(key+j)%9 for key in range(17)]+[0]*239))
            assert native.step(ctx,t,32,a,b,valid,out)==(1 if t==7 else 0)
            if t==7:assert list(out[:17])==words()[(35+ctx)*17:(36+ctx)*17]
    assert native.reset()==0 and native.begin(5)==0
    valid=(C.c_uint32*16)(1,*([0]*15))
    for t in range(8):
        for ctx in range(5):
            a=(C.c_uint16*16)(0x0001 if t==0 else 0x8000,*([0]*15))
            b=(C.c_uint16*256)(0x8001 if t==0 else 0x3f80,*([0]*255))
            assert native.step(ctx,t,32,a,b,valid,out)==(1 if t==7 else 0)
            if t==7:assert out[0]==0x80000000


def test_future_key_infinity_fixture_is_noncausal_then_selected_fault(native):
    a=(C.c_uint16*16)();b=(C.c_uint16*256)();b[16]=0x7f80
    out=(C.c_uint32*4096)();valid=(C.c_uint32*16)(*range(1,17))
    assert native.reset()==0 and native.begin(1)==0
    for t in range(8):assert native.step(0,t,32,a,b,valid,out)==(1 if t==7 else 0)
    assert out[16]&0x7f800000==0x7f800000 and out[16]&0x007fffff
    assert native.reset()==0 and native.begin(1)==0
    valid=(C.c_uint32*16)(17,*([0]*15))
    assert native.step(0,0,32,a,b,valid,out)==-2


def test_real_wiring_bounded_driver_and_no_reference_injection():
    s=(HERE/'QkNumericProbe.scala').read_text();c=(HERE/'qk_numeric.cpp').read_text()
    assert 'Module(new MatrixPipelineProbe)' in s and 'io.tap.valid:=matrix.io.result.fire' in s
    assert 'matrix.io.result.valid:=' not in s and 'Flipped(Decoupled(new MatrixStreamResult))' not in s
    assert 'std::array<uint32_t,81920/4>' in c and 'cycles<20000' in c
    assert 't->allSteps==89' in c and 'fold_softmax_rtl=0' in c
    assert not re.search(r'd\.io_(?:operand|start)[^;\n]*tailExpected',c)
    assert 'std::fma' not in c and 'fmaf(' not in c


def test_cpp_syntax_with_declared_port_stub_only(tmp_path):
    c=(HERE/'qk_numeric.cpp').read_text()
    names=set(re.findall(r'd\.(io_[A-Za-z0-9_]+)',c))
    fields=[]
    for name in sorted(names):
        if re.fullmatch(r'io_tap_bits_data_\d+',name):fields.append(f'uint32_t {name}[256]={{}};')
        elif name=='io_operand_bits_a':fields.append(f'uint32_t {name}[8]={{}};')
        elif name=='io_operand_bits_b':fields.append(f'uint32_t {name}[128]={{}};')
        elif name=='io_write_bits_data':fields.append(f'uint32_t {name}[8]={{}};')
        else:fields.append(f'uint64_t {name}=0;')
    (tmp_path/'VQkNumericProbe.h').write_text('#include <cstdint>\nstruct VQkNumericProbe {unsigned clock=0,reset=0; void eval(){};'+''.join(fields)+'};\n')
    (tmp_path/'verilated.h').write_text('struct Verilated {static void commandArgs(int,char**) {}};\n')
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-fsyntax-only',
        '-I'+str(tmp_path),'-I'+str(HERE),str(HERE/'qk_numeric.cpp')],check=True,capture_output=True,timeout=30)


def test_runner_is_syntax_valid_fixed_budget_and_preserves_failure_receipts(tmp_path):
    s=(HERE/'run_numeric.sh').read_text()
    subprocess.run(['bash','-n',str(HERE/'run_numeric.sh')],check=True)
    assert '1500-(SECONDS-START)' in s and 'cpp_compile_link 600' in s and 'verilator_generate 300' in s
    assert 'scala_compile 180' in s and 'rtl_emit 120' in s and 'real_numeric_simulation 60' in s
    assert '93e9747504fa1da6473560341febbfae6c5e917768633a84fc9ef12299293207' in s
    assert '3a3de73632a06826b1bd9c65a0a2e92b32016845' in s
    assert '-f "$OUT/idma.f"' not in s and 'run_pipeline_components.sh' not in s
    fn=s[s.index("ACTIVE_PID='' ACTIVE_NAME=''"):s.index('\ncd "$ROOT"')]
    # The local container has no GNU time. Only stub its measurement wrapper;
    # use the exact runner stage and real GNU timeout to test error receipts.
    timer=tmp_path/'time_stub.py'
    timer.write_text('import subprocess,sys\nfrom pathlib import Path\np=subprocess.run(sys.argv[5:])\nPath(sys.argv[4]).write_text("0.0 0\\n")\nsys.exit(p.returncode)\n')
    fn=fn.replace('/usr/bin/time','python3 '+str(timer))
    for name,command,want in [('failure','exit 7',7),('timeout','sleep 3',124)]:
        out=tmp_path/name;out.mkdir()
        script=f'OUT="{out}"; START=$SECONDS; '+fn+f'\nstage {name} 1 bash -c "{command}"\n'
        p=subprocess.run(['bash','-e','-o','pipefail','-c',script],capture_output=True,text=True,timeout=5)
        assert p.returncode==want
        assert (out/'stages.tsv').read_text().strip().endswith('\t'+str(want))

    # Exercise the actual TERM trap via an outer GNU timeout and a direct signal.
    # Worker plus grandchild are synthetic; no compiler/RTL process is launched.
    worker=tmp_path/'worker.py'
    worker.write_text('import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n'
        'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
        'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"])\n'
        'Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid,os.getpgrp()]))\n'
        'time.sleep(30)\n')
    def alive(pid):
        path=Path(f'/proc/{pid}/stat')
        return path.exists() and path.read_text().split(') ',1)[1][0] not in ('Z','X')
    for mode in ('outer-timeout','direct-term','inner-timeout','launch-term'):
        out=tmp_path/mode;out.mkdir()
        cap=1 if mode=='inner-timeout' else 20
        pidfile=out/'pids.json'
        active_fn=fn
        if mode=='launch-term':
            # Inject at the exact formerly unsafe window, without production hooks.
            active_fn=fn.replace('  ACTIVE_PID=$!',
                '  while [[ ! -s "'+str(pidfile)+'" ]]; do sleep 0.01; done\n'
                '  kill -TERM "$$"\n  kill -HUP "$$"\n  ACTIVE_PID=$!')
        script=f'OUT="{out}"; START=$SECONDS; '+active_fn+f'\nstage inner {cap} python3 "{worker}" "{pidfile}"\n'
        command=['bash','-e','-o','pipefail','-c',script]
        if mode=='outer-timeout':command=['timeout','--signal=TERM','--kill-after=10','1']+command
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        pids=[]
        try:
            deadline=time.monotonic()+3
            while not pidfile.exists() and time.monotonic()<deadline:time.sleep(0.02)
            assert pidfile.exists()
            pids=json.loads(pidfile.read_text())
            if mode=='direct-term':proc.send_signal(signal.SIGTERM)
            stdout,stderr=proc.communicate(timeout=8)
            assert proc.returncode==(143 if mode in ('direct-term','launch-term') else 124),(stdout,stderr)
            assert (out/'stages.tsv').read_text().strip().endswith('\t'+('124' if mode=='inner-timeout' else '143'))
            deadline=time.monotonic()+1
            while any(alive(pid) for pid in pids[:2]) and time.monotonic()<deadline:time.sleep(0.02)
            assert not any(alive(pid) for pid in pids[:2]),(mode,pids)
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
            if pids and any(alive(pid) for pid in pids[:2]):
                try:os.killpg(pids[2],signal.SIGKILL)
                except ProcessLookupError:pass
