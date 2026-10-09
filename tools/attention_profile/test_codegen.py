"""Codegen stage isolation, exact-SV guard, and the process-tree budget."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys
from types import SimpleNamespace
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_codegen as C
import run_profile as P


def original():
    root=Path(os.environ.get('ATTENTION_PROFILE_SOURCE_ROOT',P.DIAGNOSTIC_ROOT))
    return subprocess.check_output(['git','-C',str(root),'show',P.PIN+':chisel/continuous_prefill/scripts/run_host_bf16_attention_core_gate.sh'])


def test_codegen_keeps_original_argv_and_stops_before_cpp(tmp_path):
    root=tmp_path/'source with spaces'
    raw=original()
    text=C.codegen_builder(raw,root)
    base=P.relocated_builder(raw,root,root/'chisel/continuous_prefill/tests/host_bf16_attention_core.cpp')
    assert text==base.split(C.BUILD_STOP,1)[0]+C.POST_CODEGEN_CHECKS+'echo CODEGEN_ONLY_STOP_BEFORE_CPP_BUILD\nexit 0\n'
    assert 'hier_verilation >"$OUT/hierarchy_verilation.log" 2>&1' in text
    assert C.BUILD_STOP not in text
    assert text.count(C.POST_CODEGEN_CHECKS)==1
    assert text.index('hier_verilation >')<text.index(C.POST_CODEGEN_CHECKS)
    assert text.count(P.rtl_admission_guard())==1
    assert text.index(P.rtl_admission_guard())<text.index('MAKEFLAGS=-n verilator')
    assert '--expand-limit' not in text
    assert '--comp-limit-parens 16 --output-split 3000 --output-split-cfuncs 200' in text
    assert 'native_weight_hierarchy.vlt' in text
    assert 'profile_driver.cpp' not in text
    p=tmp_path/'codegen.sh';p.write_text(text)
    subprocess.run(['bash','-n',str(p)],check=True)


def test_missing_build_or_hierarchy_boundary_is_rejected(tmp_path):
    raw=original()
    with pytest.raises(ValueError,match='C\\+\\+ build boundary'):
        C.codegen_builder(raw.replace(C.BUILD_STOP.encode(),b'changed'),tmp_path)
    with pytest.raises(ValueError,match='child/top Verilation'):
        C.codegen_builder(raw.replace(b'hier_verilation >',b'not_hier_target >'),tmp_path)


def test_codegen_supervisor_is_bounded_and_does_not_enter_profile_worker(tmp_path,monkeypatch):
    seen={}
    def supervise(command,timeout_seconds):
        seen.update(command=command,seconds=timeout_seconds)
        return {'returncode':0,'forced_shutdown':False}
    monkeypatch.setattr(C,'args',lambda:object())
    monkeypatch.setattr(C,'checked_paths',lambda a:(tmp_path/'source',tmp_path/'out'))
    monkeypatch.setattr(C,'imports',lambda source:SimpleNamespace(supervise_process=supervise))
    monkeypatch.setattr(C,'finalize_supervision',lambda out,result:result['returncode'])
    with pytest.raises(SystemExit) as done:C.main()
    assert done.value.code==0 and seen['seconds']==1200
    assert 'from run_codegen import worker_entry' in seen['command'][2]
    assert 'run_profile import worker_entry' not in seen['command'][2]


def test_exact_sampled_cpp_files_are_pinned_without_normalization():
    assert C.EXPECTED_CPP=={
        'obj/VHostBlockTop___024root__DepSet_h74254c49__13.cpp':'8c97e4003108d2ff4dc356546d4ddfa922cfbd3968293ba7ca3df27bfa0d06f8',
        'obj/VHostBlockTop___024root__DepSet_h74254c49__94.cpp':'f1b680a5fb3ff465a4a8885e7e3c8c0da4a049fa12ae4c07fe4ba79a4c90b87f'}
