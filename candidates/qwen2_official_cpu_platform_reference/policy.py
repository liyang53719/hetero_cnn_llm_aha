"""New reference policy only; no historical output hashes are imported."""
import hashlib
import json

PROFILE='avx2-aten-gemm-v1'
ORIGINAL_PINS='candidates/qwen2_fullblock_reference_m128/pins.json'
ORIGINAL_PINS_SHA256='48e20d380cfc6ac0ab5b9e1690bb507e37cf99468b0df8e79a1d37da0f16110f'
PACKAGE='candidates/qwen2_official_cpu_platform_reference'
FILES=('policy.py','validator.py','test_validator.py','capture_source.py','test_capture_source.py','recipe.py','issuer.py','lifecycle.py','guard.py','test_launch.py','pair.py','test_pair.py','README.md')
PAIR_WORKFLOW='.github/workflows/qwen2-official-cpu-platform-pair.yml'
PLATFORM_SOURCE='candidates/qwen2_fullblock_ci_dut/platform_freeze.py'
DUT_PINS='candidates/qwen2_live_fullblock_model_m128/pins.json'
DUT_PINS_SHA256='a8085fe405084b4b415ae4927d85148f698b1437c05c69cbe2e07dc2feaac9f8'
RAW_ROOTS=dict(prefix_raw='work/qwen2_live_qkv_inputs_m128/ci01/raw',
               tail_raw='work/qwen2_live_tail_acquisition_m128/ci01/raw')


def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def policy():
    return dict(schema=1,contract_id='official-ast-ci-aten-avx2-reference-v1',status='PENDING_SOURCE_AND_REFERENCE_REVIEW',
        scope='SAME_FIXED_CI_ENVIRONMENT_ONLY',profile=PROFILE,
        original_pins_sha256=ORIGINAL_PINS_SHA256,geometry_source=ORIGINAL_PINS,raw_roots=dict(RAW_ROOTS),
        dut_gate_pins=dict(path=DUT_PINS,sha256=DUT_PINS_SHA256),
        original_math=dict(model_ast_nodes=38,activation_ast_nodes=14,unchanged=True),
        backend=dict(mkldnn_enabled=False,aten_cpu_capability='AVX2',threads=4,interop_threads=1,deterministic_algorithms=True),
        platform_observer=PLATFORM_SOURCE,loaded_libpython_required=True,full_system_closure=False,
        legacy_expected_hashes='DIAGNOSTIC_ONLY',legacy_failures_preserved=True,
        dut_error_gates='UNCHANGED_EXISTING_GATES',dut_authorized=False,
        reference_freeze_available=False,numerical_acceptance_claimed=False)


def original(raw):
    if type(raw) is not bytes or sha(raw)!=ORIGINAL_PINS_SHA256:raise ValueError('original geometry source drift')
    return json.loads(raw)


def geometry(raw):
    # Only original public geometry/dtype fields, never prior expectations or
    # frozen observed hashes/strides. This is not a duplicated reference manifest.
    pins=original(raw)
    return {name:{key:spec[key] for key in ('shape','bytes','native_dtype','export_dtype','native_bytes')}
            for name,spec in pins['references'].items()}
