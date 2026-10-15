"""Explicit runtime profile selection; no automatic dispatch or numerical claim.

The default retains the original AVX512 pins. Both explicit AVX2 candidates
change only the three reviewed pin fields below. The separate backend request
is returned by disable_mkldnn(); it is not added to the original pin schema. ATEN_CPU_CAPABILITY controls ATen dispatch;
it does not establish a whole-process ISA restriction or reference acceptance.
No environment writes, native imports, runtime probing, or file I/O occur here.
"""
import copy
import os

PROFILE_ENV = 'QWEN2_CI_RUNTIME_PROFILE'
CANDIDATE = 'avx2-candidate-v1'
ATEN_GEMM_CANDIDATE = 'avx2-aten-gemm-v1'
AVX2_BUILD_SHA256 = '4096ae2ff210db4a4da17fe7e5ef17c7715c4e4dc5d4175a9357b83bf820075a'
# Official dispatch evidence verified separately; no source fetch at runtime.
DISPATCH_SOURCE_URL = 'https://raw.githubusercontent.com/pytorch/pytorch/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/DispatchStub.cpp'
DISPATCH_SOURCE_BYTES = 11893
DISPATCH_SOURCE_SHA256 = 'b77d16444f42d6e0707c581888d5e2069c7958a01ee4cf77a432bd6d13827032'


def profile(environ=None):
    """Validate explicit profile and ATen environment; return None or an exact candidate name.

    Passing a mapping makes this a pure validation function. With no mapping,
    read the current process environment without modifying or inferring values.
    """
    environment = os.environ if environ is None else environ
    selected = environment.get(PROFILE_ENV)
    capability = environment.get('ATEN_CPU_CAPABILITY')
    if selected is None:
        if capability is not None:
            raise ValueError('default profile requires ATEN_CPU_CAPABILITY unset')
        return None
    if type(selected) is not str or selected not in (CANDIDATE, ATEN_GEMM_CANDIDATE):
        raise ValueError('unknown explicit CI runtime profile')
    if type(capability) is not str or capability != 'avx2':
        raise ValueError('AVX2 candidate requires explicit ATEN_CPU_CAPABILITY=avx2')
    if selected == ATEN_GEMM_CANDIDATE and any(
            key in environment for key in ('ONEDNN_MAX_CPU_ISA', 'DNNL_MAX_CPU_ISA', 'MKL_CBWR')):
        raise ValueError('undeclared backend override in ATen GEMM candidate')
    return selected


def selected(environ=None):
    """Return whether either explicitly validated AVX2 candidate is selected."""
    return profile(environ) is not None


def disable_mkldnn(environ=None):
    """Explicit backend request only, not evidence of an applied setting.

    Fresh Torch workers must set mkldnn.enabled=False and verify it before
    capture when True. False leaves defaults untouched. The lifecycle review
    must bind this profile and its assertion separately from original pins.
    This does not identify the kernel that actually executes or claim a PASS.
    """
    return profile(environ) == ATEN_GEMM_CANDIDATE


def mkldnn_enabled(environ=None):
    """Return False for the explicit new candidate, otherwise None (no change)."""
    return False if disable_mkldnn(environ) else None


def apply(pins, environ=None):
    """Return a deep copy; the candidate changes exactly three existing fields."""
    selected = profile(environ)
    result = copy.deepcopy(pins)
    if selected is None:
        return result
    if (type(result) is not dict or
            type(result.get('capture_environment')) is not dict or
            type(result.get('runtime_requirements')) is not dict or
            'ATEN_CPU_CAPABILITY' not in result['capture_environment'] or
            not {'capability','torch_build_sha256'} <= result['runtime_requirements'].keys()):
        raise ValueError('runtime pin fields required')
    result['capture_environment']['ATEN_CPU_CAPABILITY'] = 'avx2'
    result['runtime_requirements']['capability'] = 'AVX2'
    result['runtime_requirements']['torch_build_sha256'] = AVX2_BUILD_SHA256
    return result
