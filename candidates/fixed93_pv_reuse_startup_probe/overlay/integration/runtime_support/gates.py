"""Exact full-launch admission; no historical activation or preseal oracle reads.

The reviewed wrapper loads and hashes the thirteen checkpoint inputs before
installing this audit hook. Once installed, only fourteen readonly producer
roles are operands; raw checkpoint provenance and frozen oracle bytes reopen
only after the fresh public21/17-owner/one-launch-result output seal.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import types

from candidates.qwen2_live_attention_model_m128_bounded.v2 import gates as v2
from . import recipe as R
from . import closure

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parents[1]
ROOT = CANDIDATE / 'source'
OUTPUT_ROOT = CANDIDATE / 'work/fixed93_fullblock'
DATA_LOGICAL = 'work/qwen2_recovered_inputs/typed'
REFERENCE_LOGICAL = R.REFERENCE
DATA = R.frozen_layout().input_directory
TAIL_INPUTS = DATA
REFERENCE = R.frozen_layout().reference_directory
ROLES = frozenset(('x', 'gamma0', 'wq', 'wk', 'wv', 'bq', 'bk', 'bv', 'rope',
                   'wo', 'gamma1', 'wg', 'wu', 'wd'))
REFERENCES = R.NAMES
REFERENCE_METADATA = tuple(sorted(R.METADATA_NAMES | {'SEAL.json'}))
# Exact CPython 3.12 runtime helper used only for fd-relative output cleanup.
SHUTIL_SOURCE_SHA256 = '53496e06742fe008fee2bccc8caeac77473e69923bec05358bd43eea467db1f8'
require, sha, manifest = v2.require, v2.sha, v2.manifest


ORIGINAL_PINS = ROOT/'candidates/qwen2_live_fullblock_model_m128/pins.json'
ORIGINAL_PINS_SHA256='a8085fe405084b4b415ae4927d85148f698b1437c05c69cbe2e07dc2feaac9f8'
LOST_HISTORICAL_EVIDENCE=('work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/bootstrap/BOOTSTRAP_REFERENCE.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/bootstrap/SEAL.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/BOUNDARY_AFTER.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/BOUNDARY_BEFORE.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/REFERENCE.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/SEAL.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/WRAPPER_AFTER.json', 'work/qwen2_fullblock_reference_capture_20261014/fullblock_pair_v2/frozen/WRAPPER_BEFORE.json', 'work/qwen2_fullblock_reference_capture_review_20261014/bootstrap_v2_review/BOOTSTRAP_REVIEW.json', 'work/qwen2_fullblock_reference_map_20261014/AUDIT.json', 'work/qwen2_fullblock_reference_map_20261014/REPORT.md', 'work/qwen2_fullblock_reference_map_20261014/SEAL.json', 'work/qwen2_fullblock_reference_map_20261014/official_dependency/SOURCE_RECEIPT.json', 'work/qwen2_fullblock_reference_map_20261014/official_dependency/activations.py', 'work/qwen2_live_attention_reference_m128/control/frozen01/CAPTURE_EXECUTION.json', 'work/qwen2_live_attention_reference_m16_20261014/bootstrap01/control/RESULT.json', 'work/qwen2_live_qkv_inputs_m128/frozen01/inputs/INPUTS_READY.json', 'work/qwen2_live_qkv_inputs_m128/frozen01/raw/subset_manifest.json', 'work/qwen2_live_tail_inputs_m128/reconstruct01/inputs/INPUTS_READY.json', 'work/qwen2_tail_inputs_independent_review_20261014/REPORT.md', 'work/qwen2_tail_ranges_20261014/tail_manifest.json')

def _local_binding():
    path=R.safe_path(ROOT,R.FROZEN_BINDING)
    require(path.stat().st_size<=262144,'bounded local oracle binding')
    raw=path.read_bytes()
    require(R.sha(raw)==R.digest(os.getenv(R.BINDING_ENV)),'externally bound local oracle identity')
    value=R.parse(raw)
    R.fields(value,dict(schema=1,status=R.STATUS,old_pass_inherited=False,numerical_acceptance_claimed=False),
             'honest local bootstrap binding')
    return value


def pins():
    require(sha(ORIGINAL_PINS)==ORIGINAL_PINS_SHA256,'original execution pins')
    original=R.parse(ORIGINAL_PINS.read_bytes());binding=_local_binding()
    dependencies={n:v['sha256'] for n,v in closure.source_manifest(ROOT).items()}
    rp=R.load_pins(ROOT);art=R.artifact_binding()
    for name in REFERENCE_METADATA:
        dependencies[REFERENCE_LOGICAL+'/'+name]=art['reference_metadata'][name]['sha256']
    dependencies[R.FROZEN_BINDING]=R.digest(os.getenv(R.BINDING_ENV))
    dependencies['work/qwen2_recovered_inputs/ARTIFACTS.json']=R.digest(os.getenv('QWEN2_FIXED93_ARTIFACTS_SHA256'))
    for n,v in art['reference_proofs'].items():dependencies[n]=v['sha256']
    runtime={n:v['sha256'] for n,v in art['runtime_read_files'].items()}
    original.update(dependency_sha256=dependencies,runtime_read_sha256=runtime,
        fullblock_reference_pins_sha256=R.PINS_SHA256,frozen_contract_sha256=R.FROZEN_CONTRACT_SHA256,
        data_path=DATA_LOGICAL,reference_path=REFERENCE_LOGICAL,
        historical_receipts_revalidated=False,lost_historical_evidence=list(LOST_HISTORICAL_EVIDENCE))
    return original


def _canonical(path):
    path = Path(path).absolute()
    require(path.resolve() == path, 'aliased path refused: ' + str(path))
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'symlink path refused: ' + str(path))
    return path


def _sha_spec(path, expected):
    path = _canonical(path)
    require(path.is_file(), 'missing pinned file: ' + str(path))
    actual = R.identity(path)
    require(actual['sha256'] == expected['sha256'] and
            ('bytes' not in expected or actual['bytes'] == expected['bytes']),
            'pinned file identity drift: ' + str(path))
    return actual


def verify_dependencies():
    p = pins()
    require(p.get('scope') == 'M128_SOFTWARE_PUBLIC21_FULLBLOCK' and
            type(p.get('rows')) is int and p['rows'] == 128 and
            p.get('actual_execution_authorized') is False, 'fullblock admission scope')
    dependency = p.get('dependency_sha256')
    require(type(dependency) is dict and bool(dependency), 'source closure required')
    for name, digest in dependency.items():
        require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts and
                type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'invalid source pin')
        _sha_spec(R.frozen_path(name), {'sha256': digest})
    require(p.get('fullblock_reference_pins_sha256') == R.PINS_SHA256 and
            p.get('frozen_contract_sha256') == R.FROZEN_CONTRACT_SHA256,
            'reviewed fullblock reference code pins required')
    for key, name in (('data_path', DATA_LOGICAL), ('reference_path', REFERENCE_LOGICAL)):
        require(p.get(key) == name, 'fixed ' + key + ' binding')
    for name in REFERENCE_METADATA:
        require(REFERENCE_LOGICAL+'/'+name in dependency,
                'fresh frozen reference metadata must be source-pinned: ' + name)
    for name, digest in p.get('runtime_read_sha256', {}).items():
        path = Path(name) if Path(name).is_absolute() else R.frozen_path(name)
        _sha_spec(path, {'sha256': digest})
    return p


def admission_metadata():
    path = CANDIDATE / 'ADMISSION.json'
    expected = R.digest(os.getenv('QWEN2_FIXED93_ADMISSION_SHA256'))
    require(sha(path) == expected, 'explicit new root admission file identity required')
    value = R.parse(path.read_bytes())
    require(type(value) is dict and value.get('startup_only') is True and
         value.get('fullblock_authorized') is False and value.get('M128_authorized') is False and
         value.get('entrypoint') == 'integration/startup_probe.py' and
         value.get('stop_before') == 'first_x.advance_to_request',
         'root authority must be startup-only with the exact stop boundary')
    require(value.get('schema') == 'fixed93-startup-probe-admission-v1' and
            value.get('status') == 'REVIEWED_FIXED93_STARTUP_PROBE_ACTUAL' and
            value.get('actual_execution_authorized') is True and value.get('automatic_retry') is False,
            'new actual root admission required; stored source proposal is not authority')
    require(type(value.get('files')) is dict, 'new exact assembly file pins missing')
    for relative, spec in value['files'].items():
        _sha_spec(R.safe_path(CANDIDATE, relative), spec)
    return value


def sources():
    # Recheck new assembly too, but return only the frozen306 DUT-source map.
    admission_metadata()
    verify_dependencies()
    return {name: spec['sha256'] for name, spec in closure.source_manifest(ROOT).items()}


def require_review(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}',value),
            'explicit reviewed source-only DUT closure required')
    admission_metadata()
    require(value==R.digest(os.getenv(R.CLOSURE_ENV))==closure.digest(ROOT),
            'reviewed source-only DUT closure drift')
    return sources()


def require_budget():
    """No caller/CLI timing override and no inherited pc12 deadline."""
    authority = admission_metadata()
    budget = CANDIDATE / 'BUDGET_PROPOSAL.json'
    require(authority.get('budget_reviewed') is True and 'BUDGET_PROPOSAL.json' in authority['files'],
            'new root-reviewed wholeblock budget admission missing')
    _sha_spec(budget, authority['files']['BUDGET_PROPOSAL.json'])
    value = R.parse(budget.read_bytes())
    require(value.get('schema') == 'fixed93-startup-probe-resource-v1' and
         value.get('startup_only_scope_required') is True and value.get('wholeblock_scope_required') is False and
         value.get('inner_wall_seconds') == 30 and value.get('outer_wall_seconds') == 45 and
         value.get('rss_bytes') == 2147483648 and value.get('one_cpu') is True and
         value.get('output_bytes') == 16777216 and value.get('file_bytes') == 8388608 and
         value.get('sample_rows') == 46 and value.get('automatic_retry') is False,
         'exact startup-only bounded resource scope required')
    require(value.get('status') == 'REVIEWED_FIXED93_STARTUP_PROBE_BUDGET',
            'fullblock budget unreviewed; representative timing and fixed source budget required')
    for key in ('inner_wall_seconds', 'outer_wall_seconds', 'rss_bytes', 'output_bytes',
                'file_bytes', 'log_bytes', 'progress_loop_interval'):
        require(type(value.get(key)) is int and value[key] > 0, 'reviewed positive integer budget: ' + key)
    require(value['outer_wall_seconds'] >= value['inner_wall_seconds'] + 7,
            'outer watchdog must reserve seven seconds beyond the inner deadline')
    require(value.get('automatic_retry') is False, 'automatic retry must remain disabled')
    require(value['progress_loop_interval'] == 131072, 'unchanged Attention progress interval required')
    require(type(value.get('poll_seconds')) in (int, float) and 0 < value['poll_seconds'] <= 1,
            'reviewed bounded poll_seconds required')
    require(value['file_bytes'] <= value['output_bytes'], 'file cap must fit total output cap')
    return value


def data_path(value):
    require(type(value) is str and value == DATA_LOGICAL, 'exact published prefix input directory required')
    require(_canonical(DATA).is_dir(), 'prefix input directory missing')
    return DATA


def reference_path(value):
    require(type(value) is str and value == REFERENCE_LOGICAL,
            'exact fresh frozen fullblock reference directory required')
    require(_canonical(REFERENCE).is_dir(), 'frozen reference directory missing')
    return REFERENCE


def fresh_output(out, data):
    out = _canonical(out)
    require(out.parent == OUTPUT_ROOT and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', out.name),
            'output must be a fresh direct child of fullblock numeric work directory')
    require(not out.exists() and Path(data) == DATA and
            all(not out.is_relative_to(p) and not p.is_relative_to(out) for p in R.frozen_layout().frozen_roots),
            'output exists/overlaps inputs or reference')


def reference_recipe():
    p = verify_dependencies()
    rp = R.load_pins(ROOT)
    R.source_check(ROOT, rp)
    frozen = R.require_frozen_references(rp, ROOT)
    require(p['fullblock_reference_pins_sha256'] == R.PINS_SHA256, 'fullblock recipe identity drift')
    return rp, frozen


def require_final_reference():
    rp, frozen = reference_recipe()
    require(set(rp['producer_roles']) == ROLES and len(rp['raw_tensors']) == 13 and
            set(frozen['outputs']) == REFERENCES, 'exact 14-role/13-raw/29-reference contract required')
    validate_reference_metadata(DATA, REFERENCE, recipe=(rp, frozen))
    return pins()


def validate_reference_metadata(data,reference,*,recipe=None):
    """Honest fresh-bootstrap metadata; no reference operand opens before seal."""
    require(Path(data)==DATA and Path(reference)==REFERENCE,'fixed input/reference namespaces required')
    rp,frozen=reference_recipe() if recipe is None else recipe
    R.fields(frozen,dict(status=R.STATUS,bootstrap_status_preserved=False,fixed_expectations_match=True,
        old_pass_inherited=False,oracle_payload_read=False),'locally bound current bootstrap oracle')
    current=R.validate_bootstrap_metadata(rp,seal_sha256=frozen['bootstrap_seal']['sha256'])
    require(R.same(current['outputs'],frozen['outputs']) and
            R.same(current['bootstrap_manifest'],frozen['bootstrap_manifest']),'bootstrap binding metadata drift')
    return current['manifest']


def _input_specs():
    rp = R.load_pins(ROOT)
    require(set(rp['producer_roles']) == ROLES, 'exact fourteen executable input roles required')
    return rp


def input_identity():
    rp = _input_specs()
    return {name: _sha_spec(R.frozen_path(spec['path']), spec) for name, spec in rp['producer_roles'].items()}


def raw_identity(data):
    require(Path(data) == DATA, 'fixed raw provenance input required')
    rp = _input_specs()
    require(len(rp['raw_tensors']) == 13, 'exact thirteen raw provenance tensors required')
    return {spec['local_name']: _sha_spec(R.frozen_path(spec['path']), spec) for spec in rp['raw_tensors']}


def evidence_identity(names=None):
    """Rehash exact metadata files while retaining their logical record keys."""
    rp = R.load_pins(ROOT)
    expected = {spec['path'] for spec in rp['input_metadata'].values()}
    expected |= {REFERENCE_LOGICAL+'/'+name for name in REFERENCE_METADATA}
    require(names is None or set(names) == expected, 'exact frozen evidence metadata required')
    return {name: R.identity(R.frozen_path(name))['sha256'] for name in sorted(expected)}


def reference_identity(name):
    require(name in REFERENCES, 'exact frozen reference name required')
    return R.identity(R.frozen_path(REFERENCE_LOGICAL+'/'+name+'.f32le'), reference_opened=True)


def validate_inputs(data, reference):
    rp, frozen = reference_recipe()
    ref = validate_reference_metadata(data, reference, recipe=(rp, frozen))
    inputs = {name: R.checked(ROOT, spec['path'], spec) for name, spec in rp['producer_roles'].items()}
    require(set(inputs) == ROLES, 'exact fourteen executable input roles required')
    ready = dict(status='PINNED_FULLBLOCK_FOURTEEN_READONLY_INPUTS_READY',
        roles={name:spec['record'] for name,spec in rp['producer_roles'].items()})
    # Original prefix-nine records predate the readonly metadata field. Their
    # immutable role identities are checked by recipe.metadata_check; the live
    # fixture/PhysicalMemory binding independently enforces readonly providers.
    require(all(ready['roles'][name]['readonly'] is True for name in ('wo','gamma1','wg','wu','wd')),
            'tail initial roles must remain readonly')
    evidence = evidence_identity()
    raw = raw_identity(data)
    return inputs, ready, evidence, dict(raw_tensors=raw, raw_payloads_rehashed_before_gate=13,
        raw_tensor_metadata={s['local_name']:{k:s[k] for k in ('bytes','sha256')} for s in rp['raw_tensors']},
        input_roles=14, input_identity={name:{k:spec[k] for k in ('bytes','sha256')}
                                      for name,spec in rp['producer_roles'].items()},
        official_reference_nodes_metadata=len(ref['outputs']), reference_payloads_read_before_seal=0,
        source_pin_sha256=R.PINS_SHA256, frozen_contract_sha256=R.FROZEN_CONTRACT_SHA256,
        full_checkpoint_sha256_verified=False, saved_actual_inputs_loaded=False)


def _token_bytes(name, raw, shape):
    if name not in R.TOKEN_MAJOR:
        return raw
    batch, heads, tokens, width = shape
    require(batch == 1, 'fixed single-batch reference layout')
    stride = width * 4
    return b''.join(raw[(head*tokens+token)*stride:(head*tokens+token+1)*stride]
                    for token in range(tokens) for head in range(heads))


def validate_references(data, reference):
    rp, frozen = reference_recipe()
    ref = validate_reference_metadata(data, reference, recipe=(rp, frozen))
    values = {}
    for name, spec in ref['outputs'].items():
        raw = R.checked(ROOT, REFERENCE_LOGICAL+'/'+spec['file'], spec, reference_opened=True)
        require(R.sha(_token_bytes(name, raw, spec['shape'])) == spec['token_major_sha256'],
                'fixed reference layout identity drift: '+name)
        native = bytearray()
        for (word,) in struct.iter_unpack('<I', raw):
            require(word & 0x7f800000 != 0x7f800000, 'nonfinite frozen reference: '+name)
            if name == 'softmax_fp32':
                native.extend(struct.pack('<I', word))
            else:
                require(word & 0xffff == 0, 'reference must be exact BF16 widening: '+name)
                native.extend(struct.pack('<H', word >> 16))
        require(R.sha(native) == spec['native_sha256'], 'native reference identity drift: '+name)
        values[name] = raw
    mask = R.checked(ROOT, REFERENCE_LOGICAL+'/mask.bf16le',
        dict(bytes=rp['mask_contract']['native_bytes'], sha256=rp['mask_contract']['native_sha256']),
        reference_opened=True)
    expected = b''.join(struct.pack('<H', 0 if k <= q else 0xff7f) for q in range(128) for k in range(128))
    require(mask == expected and values['mask'] == b''.join(struct.pack('<I', w << 16)
            for (w,) in struct.iter_unpack('<H', mask)), 'exact native/export mask correspondence')
    require(values['cache_k'] == values['k'] and
            _token_bytes('cache_v',values['cache_v'],ref['outputs']['cache_v']['shape']) == values['v'] and
            _token_bytes('pv',values['pv'],ref['outputs']['pv']['shape']) == values['att'],
            'cold cache/PV correspondence drift')
    return ref, values


def correspondence():
    document = R.parse(closure.MANIFEST.read_bytes())
    hashes, sizes = document['selected_source_sha256'], document['selected_source_bytes']
    require(type(hashes) is dict and hashes and hashes.keys() == sizes.keys(), 'selected source witnesses missing')
    for relative, expected in hashes.items():
        _sha_spec(R.safe_path(CANDIDATE/'selected', relative), dict(bytes=sizes[relative],sha256=expected))
    return dict(status='FIXED93_SELECTED_SOURCE_IDENTITY_ONLY',selected_source_sha256=hashes,
        selected_source_bytes=sizes,old_pv32_correspondence_inherited=False,rtl_executed=False,
        scala_host_executed=False,hardware_cycles=None,source_to_rtl_equivalence_proven=False,
        retained_backend_scoped_profiles=['QKV two-partial pair_reverse','original Down split-K workspace'])


class OracleGate(v2.OracleGate):
    """Preserve exact v2 native/FENV admission, replace extension-based payload rules.

    All unlisted work files are forbidden, including historical .json/.u32le/
    .presence and extensionless data. This hook is a source-reviewed orchestration
    guard, not a sandbox for arbitrary native code or adversarial Python.
    """
    def __init__(self, data, out, reference):
        require(Path(data) == DATA and Path(reference) == REFERENCE, 'fixed fullblock gate namespaces')
        v2.base.original.OracleGate.__init__(self,data,_canonical(out),reference)
        p2=v2.pins()
        self.scalar_path=ROOT/p2['scalar_source']
        require(sha(self.scalar_path)==p2['scalar_source_sha256'],'Scalar source drift')
        scalar_code=v2.code_in(compile(self.scalar_path.read_text(),str(self.scalar_path),'exec',
            dont_inherit=True,optimize=sys.flags.optimize),'ScalarService')
        self.expected_init=v2.code_in(scalar_code,'__init__')
        self.expected_environment=v2.code_in(scalar_code,'_check_environment')
        self.ctypes_path=_canonical(Path(ctypes.__file__).resolve())
        require(self.ctypes_path.is_relative_to(Path(sys.base_prefix).resolve()) and
            sha(self.ctypes_path)==p2['ctypes_runtime']['sha256'],'exact relocated ctypes source')
        ctypes_code=v2.code_in(compile(self.ctypes_path.read_text(),str(self.ctypes_path),'exec',
            dont_inherit=True,optimize=sys.flags.optimize),'CDLL')
        self.expected_ctypes={n:v2.code_in(ctypes_code,n) for n in ('__init__','__getitem__','__getattr__')}
        self.environment_events=[];self.environment_handle=None;self.artifact_reads=[]
        require(self.out.parent == OUTPUT_ROOT, 'fullblock output namespace required')
        p = verify_dependencies()
        from . import native_artifact
        self.artifacts={name:Path(spec['path']) for name,spec in native_artifact.identity().items()}
        rp = R.load_pins(ROOT)
        self.input_paths = {R.frozen_path(s['path']) for s in rp['producer_roles'].values()}
        self.raw_paths = {R.frozen_path(s['path']) for s in rp['raw_tensors']}
        self.reference_paths = {R.frozen_path(REFERENCE_LOGICAL+'/'+n+'.f32le') for n in REFERENCES}
        self.reference_paths |= {R.frozen_path(REFERENCE_LOGICAL+'/mask.bf16le')}
        require((len(self.input_paths), len(self.raw_paths), len(self.reference_paths)) == (14, 13, 30),
                'exact input/raw/reference path counts required')
        self.metadata_paths = {R.frozen_path(name) for name in p['dependency_sha256']}
        assembly = admission_metadata()
        self.metadata_paths |= {R.safe_path(CANDIDATE,name) for name in assembly['files']}
        self.metadata_paths |= {CANDIDATE/'ADMISSION.json', closure.MANIFEST}
        # The installed observer revalidates these immutable fixed93 witnesses
        # at construct/enter/exit. Admit only the nine already-reviewed files,
        # after the original correspondence helper rechecks both bytes and SHA.
        selected = correspondence()
        selected_hashes, selected_sizes = selected['selected_source_sha256'], selected['selected_source_bytes']
        require(type(selected_hashes) is dict and type(selected_sizes) is dict and
                selected_hashes.keys() == selected_sizes.keys() and len(selected_hashes) == 9,
                'exact nine selected hash/size witnesses required')
        require(all(type(name) is str and type(selected_sizes[name]) is int and selected_sizes[name] >= 0 and
                    type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
                    for name, digest in selected_hashes.items()), 'typed selected source pins required')
        self.selected_source_paths = {_canonical(R.safe_path(CANDIDATE/'selected', name))
                                      for name in selected_hashes}
        require(len(self.selected_source_paths) == 9 and not self.selected_source_paths &
                (self.input_paths | self.raw_paths | self.reference_paths),
                'selected source witnesses cannot bypass payload policy')
        self.metadata_paths |= self.selected_source_paths
        # The fullblock reference recipe transitively pins preserved M16/M128
        # source closures. source_check rehashes these exact files after seal;
        # denying them would recreate the old postseal validation self-lock.
        self.metadata_paths |= {R.frozen_path(name) for name in rp['sources']}
        for preserved_closure in rp['preserved_execution_closures'].values():
            self.metadata_paths |= {R.frozen_path(name) for name in preserved_closure['sha256']}
        domains = (self.input_paths, self.raw_paths, self.reference_paths, self.metadata_paths)
        require(all(not left & right for index, left in enumerate(domains) for right in domains[index+1:]),
                'input/raw/reference/metadata allowlists must be disjoint')
        # Local package files are admitted only by the exact source closure
        # already present in dependency_sha256, never by directory enumeration.
        self.runtime_paths = {Path(n) if Path(n).is_absolute() else R.frozen_path(n)
                              for n in p.get('runtime_read_sha256', {})}
        self.runtime_paths |= {Path(s['path']) if Path(s['path']).is_absolute() else R.frozen_path(s['path'])
                               for s in rp['runtime_native_files'].values()}
        self.runtime_paths |= {self.ctypes_path}
        # New orchestration rechecks the anchored parent and already reviewed
        # runtime/codec files after this hook is installed. Admit exact pinned
        # files only, never a /proc, runtime-library or codec directory prefix.
        actual = sys.modules.get('admission')
        require(type(actual) is types.ModuleType and actual.__name__ == 'admission' and
                Path(actual.__file__).resolve() == CANDIDATE/'admission.py' and
                getattr(actual, '_USED', False) is True, 'canonical consumed admission module required')
        state = getattr(actual, '_STATE', None)
        require(type(state) is dict and state.get('pid') == os.getpid(),
                'same-process consumed admission state required')
        parent = state.get('parent')
        require(type(parent) is dict and set(parent) == {'pid', 'start_ticks'} and
                all(type(parent[k]) is int and parent[k] > 0 for k in parent) and
                parent['pid'] == os.getppid(), 'same anchored parent identity required')
        self.parent_identity_bound = dict(parent)
        self.parent_stat_path = Path('/proc')/str(parent['pid'])/'stat'
        runtime_path = CANDIDATE/'RUNTIME_PINS.json'
        _sha_spec(runtime_path, assembly['files']['RUNTIME_PINS.json'])
        runtime = R.parse(runtime_path.read_bytes())
        require(R.same(runtime, state.get('runtime_pins')) and type(runtime.get('files')) is dict,
                'admitted runtime table identity differs')
        for name, spec in runtime['files'].items():
            require(type(name) is str and Path(name).is_absolute() and type(spec) is dict and
                    set(spec) == {'bytes', 'sha256'} and type(spec['bytes']) is int and
                    spec['bytes'] >= 0 and type(spec['sha256']) is str and
                    re.fullmatch('[0-9a-f]{64}', spec['sha256']), 'exact runtime file pin required')
            self.runtime_paths.add(_canonical(name))
        codec_pins_path = CANDIDATE/'capture/CODEC_PINS.json'
        _sha_spec(codec_pins_path, assembly['files']['capture/CODEC_PINS.json'])
        codec_pins = R.parse(codec_pins_path.read_bytes())
        require(type(codec_pins) is dict and set(codec_pins) == {'format.py', 'writer.py', 'decoder.py'},
                'exact reviewed three-file codec required')
        codec_root = _canonical(require_budget()['attention_trace_limits']['codec_root'])
        for name, digest in codec_pins.items():
            path = codec_root/name
            _sha_spec(path, {'sha256': digest})
            self.runtime_paths.add(path)
        require(not self.runtime_paths & (self.input_paths | self.raw_paths | self.reference_paths),
                'runtime read pins cannot bypass operand/provenance/reference policy')
        self.shutil_path = Path(shutil.__file__).resolve()
        require(sha(self.shutil_path) == SHUTIL_SOURCE_SHA256, 'shutil cleanup source drift')
        self.expected_cleanup = v2.code_in(compile(self.shutil_path.read_text(), str(self.shutil_path),
            'exec', dont_inherit=True, optimize=sys.flags.optimize), '_rmtree_safe_fd')
        self.input_reads = []
        self.source_cache_bypasses = []
        self.cleanup_directory_reads = []

    def open_after_seal(self, seal):
        require(not self.opened and type(seal) is dict, 'one fresh whole-launch seal required')
        for key in ('actual_outputs_sealed', 'finalfence', 'same_live_identity'):
            require(seal.get(key) is True, 'whole-launch seal missing '+key)
        for key, value in (('public_completions',21), ('actual_owner_jobs',17), ('accepted_launch_results',1)):
            require(type(seal.get(key)) is int and seal[key] == value, 'whole-launch seal count: '+key)
        debt = seal.get('outstanding_debts')
        require(type(debt) is dict and all(v is None or v is False or type(v) is int and v == 0
                                         for v in debt.values()), 'whole-launch seal has outstanding debts')
        self.opened = True

    def _readonly(self, mode, flags):
        require((mode is None or isinstance(mode,str) and all(c not in mode for c in 'wa+x')) and
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_CREAT|os.O_TRUNC) == 0,
                'pinned inputs, code, provenance and references must remain read-only')

    def _deny(self, path):
        self.blocked += 1
        raise ValueError('unapproved payload/historical artifact or reference before whole-launch seal: '+str(path))

    def _cleanup_directory(self, raw, mode, flags, frame):
        """Resolve audit's omitted dir_fd only for the original shutil helper."""
        if (Path(raw).is_absolute() or frame.f_globals is not shutil.__dict__ or
                frame.f_code is not shutil._rmtree_safe_fd.__code__ or frame.f_code != self.expected_cleanup):
            return None
        require(mode is None and type(flags) is int and
                flags & ~getattr(os,'O_CLOEXEC',0) == os.O_RDONLY|os.O_NONBLOCK,
                'cleanup directory open flags drift')
        require(raw not in ('','.','..') and Path(raw).name == raw and
                frame.f_locals.get('name') == raw, 'cleanup name must be exact original directory entry')
        fd = frame.f_locals.get('dirfd')
        require(type(fd) is int and fd >= 0, 'cleanup requires original live parent dirfd')
        parent = _canonical(os.readlink('/proc/self/fd/'+str(fd)))
        path = _canonical(parent/raw)
        require(parent.is_relative_to(self.out) and path != self.out and path.is_relative_to(self.out)
                and path.is_dir() and _canonical(frame.f_locals['path']) == path,
                'cleanup directory must be inside the current output')
        require(sha(self.shutil_path) == SHUTIL_SOURCE_SHA256, 'shutil source drift at cleanup admission')
        self.cleanup_directory_reads.append(str(path.relative_to(self.out)))
        return path

    def audit(self, event, args):
        # Keep direct ctypes call frames: super().audit here would insert an
        # extra Python frame and invalidate the exact original v2 FENV proof.
        if event == 'ctypes.dlopen' and args[0] is None:
            require(not self.opened and self.environment_handle is None, 'FENV handle only once before seal')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__init__')
            self._original_environment_frames(frame.f_back)
            require(frame.f_locals.get('name') is None, 'FENV handle must target current process')
            self.environment_handle = id(frame.f_locals['self'])
            self.environment_events.append(dict(event=event, target=None,
                caller='ScalarService.__init__ -> ScalarService._check_environment -> ctypes.CDLL.__init__',
                source_sha256=v2.pins()['scalar_source_sha256'], admitted=True))
            return
        if event == 'ctypes.dlsym' and getattr(args[0], '_name', 'not-current-process') is None:
            require(id(args[0]) == self.environment_handle and args[1] == 'fegetround',
                    'current-process symbol restricted to original fegetround probe')
            frame = sys._getframe(1)
            self._ctypes_frame(frame, '__getitem__')
            self._ctypes_frame(frame.f_back, '__getattr__')
            self._original_environment_frames(frame.f_back.f_back)
            self.environment_events.append(dict(event=event, symbol='fegetround', admitted=True))
            return
        if event == 'ctypes.dlopen':
            # Same exact-target admission as the original base; artifact is now
            # the verified existing0754 ELF, possibly outside this source root.
            name = args[0]
            require(isinstance(name, (str, bytes)), 'unapproved native dlopen handle')
            path = _canonical(Path(os.fsdecode(name)))
            require(path == self.artifacts['library'], 'unapproved native dlopen path')
            self.artifact_reads.append(dict(event=event, path=str(path)))
            return
        if event == 'import' and args[0].split('.')[0] in ('torch', 'transformers'):
            self._deny(args[0])
        if event != 'open' or not isinstance(args[0], (str,bytes)):
            return
        raw = os.fsdecode(args[0])
        mode, flags = args[1], args[2]
        cleanup = self._cleanup_directory(raw, mode, flags, sys._getframe(1))
        if cleanup is not None:
            return
        # proc/self is a kernel symlink; admit only this exact observation
        # spelling before ordinary no-alias canonicalization. No proc directory
        # or other process memory/interface receives permission.
        if raw == '/proc/self/maps':
            self._readonly(mode, flags)
            return
        path = _canonical(raw)
        if path.is_relative_to(self.out):
            return
        self._readonly(mode, flags)
        if path.suffix == '.pyc':
            try:
                source = _canonical(importlib.util.source_from_cache(str(path)))
            except (ValueError, NotImplementedError):
                source = None
            if source in self.metadata_paths | self.runtime_paths and source.suffix == '.py':
                # SourceFileLoader catches this as an ordinary cache miss and
                # reads the source-bound .py; no unreviewed pyc bytes are read.
                self.source_cache_bypasses.append(str(path))
                raise FileNotFoundError(errno.ENOENT, 'use pinned source instead of bytecode cache', str(path))
        if path in self.input_paths:
            self.input_reads.append(R.frozen_name(path))
            return
        if path in self.reference_paths:
            if not self.opened:
                self._deny(path)
            self.reference_reads.append(R.frozen_name(path))
            return
        if path in self.raw_paths:
            if not self.opened:
                self._deny(path)
            self.provenance_reads.append(R.frozen_name(path))
            return
        if path in self.artifacts.values():
            self.artifact_reads.append(dict(event=event, path=str(path)))
            return
        if path in self.metadata_paths or path in self.runtime_paths:
            return
        if path == self.parent_stat_path:
            require(os.getppid() == self.parent_identity_bound['pid'], 'anchored parent PID changed')
            return
        # All lazy runtime/stdlib sources require exact immutable file pins above.
        # No site-packages or arbitrary stdlib .py/.pyc directory exemption.
        if str(path) in ('/proc/self/stat', '/proc/self/statm', '/proc/self/status'):
            return
        self._deny(path)
