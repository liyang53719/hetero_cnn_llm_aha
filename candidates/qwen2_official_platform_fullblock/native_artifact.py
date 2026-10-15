"""Load only the fresh native artifact named in the externally pinned local binding."""
import hashlib
import json
import os
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=ROOT/'work/qwen2_fullblock_ci_native/ci01'
BINDING=ROOT/'work/qwen2_official_platform_fullblock/ci01/FROZEN_BINDING.json'
BINDING_ENV='QWEN2_PLATFORM_DUT_FROZEN_BINDING_SHA256'


def canonical(path):
    if path.resolve()!=path or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('native binding path alias')
    return path


def identity():
    expected=os.environ.get(BINDING_ENV,'')
    if not re.fullmatch('[0-9a-f]{64}',expected) or expected=='0'*64:
        raise ValueError('explicit local binding identity required')
    if canonical(BINDING).stat().st_size>262144:raise ValueError('bounded native binding required')
    raw=BINDING.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('local binding drift')
    binding=json.loads(raw)
    if binding.get('status')!='LOCAL_SAME_JOB_PAIR_POLICY_CONDITIONS_SATISFIED_ORACLE_ONLY':
        raise ValueError('fresh oracle binding required')
    result={}
    for role,file,key in (('library','official_bf16_matrix_silu.so','native_library'),
                          ('receipt','official_bf16_compile.json','native_receipt')):
        path=canonical(DIRECTORY/file);spec=binding['context'][key]
        if set(spec)!={'path','bytes','sha256'} or spec['path']!=str(path.relative_to(ROOT)):
            raise ValueError('exact current native target required')
        raw=path.read_bytes();actual=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        if type(spec['bytes']) is not int or actual!={k:spec[k] for k in ('bytes','sha256')}:
            raise ValueError('bound native artifact changed')
        result[role]=dict(path=str(path),**actual)
    return result


def load(dense):
    before=identity()
    receipt=dense.verify_library(before['receipt']['path'])
    if receipt['library']!=before['library']['path'] or receipt['library_sha256']!=before['library']['sha256']:
        raise ValueError('fresh native compile receipt target mismatch')
    library=dense.configure_silu_library(dense.configure_library(dense.C.CDLL(receipt['library'])))
    if identity()!=before:raise ValueError('fresh native changed during loading')
    return library,receipt,dict(status='VERIFIED_CURRENT_CI_NATIVE_CODE',compile_executed=False,
        old_numeric_state_reused=False,old_pass_inherited=False,
        fresh_compile_receipt=receipt,artifact_identity_before=before)
