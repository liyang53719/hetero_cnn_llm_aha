#!/usr/bin/env python3
"""Freeze inputs/sources, then run public21 pc0--9 on its one physical map.

This is a NEW software-only receipt, never a rebind of an earlier FFN4 PASS.
The existing Matrix library is reusable only with identical source, binary
and strict compile receipts. A small independent prefix C++ oracle is frozen
at preparation and compiled only after the actual prefix checkpoint.
The oracle and saved stages are inaccessible until all ten actual public
completions and physical ACKs retire. Both executions stop before attention.
"""
import argparse
from contextlib import contextmanager
import ctypes as C
import hashlib
import importlib
import json
import math
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
PREFIX = 'candidates.qwen2_resident_matrix.ffn_public.'
PAYLOAD = 'work/qwen2_layer0_payload_20261011/manifest.json'
RECIPE = 'work/qwen2_block_recipe_m128_release_20261011'
SAVED = 'work/qwen2_fullgraph_dataflow_20261011/cold_m128'
CACHE = 'work/qwen2_ffn_fullgroup_20261012/actual_m128_01'
PINS = {
    PAYLOAD: '582f34afe5c52633f5290b5ba071f76164193f59d6edfc0d949658fd1e9715d1',
    RECIPE + '/RESULT.json': '18021a757aef57c94bdbd34a17a899c76df194c0ff32706baa089eefd6a3db6e',
    'work/qwen2_fullgraph_dataflow_20261011/PREPARED.json':
        '15b5043a945589cb320319035eeba82a21cc2689fc91ca42ce6bf4b5894726cb',
    SAVED + '/RESULT.json': '30614529e641616bfb3fad7857301c4a34104d5b76be92f6c9417e4c387308ae',
}
MODEL = 'Qwen/Qwen2-1.5B-Instruct'
REVISION = 'ba1cf1846d7df0a0591d6c00649f57e798519da8'
STAGES = ('n0', 'qr', 'kr', 'v', 'q', 'k')
WIDTHS = (1536, 1536, 256, 256, 1536, 256)
OUTPUTS = ('n0', 'qraw', 'qr', 'q', 'kraw', 'kr', 'k', 'vraw', 'v', 'kv')
TENSORS = {
    'embeddings': ('embed_tokens.rows_0_255', [256, 1536]),
    'gamma0': ('input_layernorm.weight', [1536]),
    'bq': ('self_attn.q_proj.bias', [1536]),
    'bk': ('self_attn.k_proj.bias', [256]),
    'bv': ('self_attn.v_proj.bias', [256]),
    'wq': ('self_attn.q_proj.weight', [1536, 1536]),
    'wk': ('self_attn.k_proj.weight', [256, 1536]),
    'wv': ('self_attn.v_proj.weight', [256, 1536]),
}
NUMERIC_SOURCES = (
    'candidates/qwen2_resident_matrix/ffn_window/numeric_recipe.cpp',
    'candidates/qwen2_resident_matrix/ffn_tiles/silu_recipe.cpp',
    'candidates/qwen2_resident_matrix/transposed_down/numeric_smoke.cpp',
)
_runtime = None
_import_hashes = None
_imported_python_paths = None


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while raw := stream.read(1 << 20):
            digest.update(raw)
    return digest.hexdigest()


def checked_json(relative, digest=None):
    path = ROOT / relative
    raw = path.read_bytes()
    require(sha(raw) == (digest or PINS[relative]), 'pinned metadata changed: ' + relative)
    return json.loads(raw)


def source_paths():
    """Extend the old utility's closure without invoking its receipt/runtime."""
    sys.path.insert(0, str(ROOT)) if str(ROOT) not in sys.path else None
    helper = importlib.import_module(PREFIX + 'check_numeric')
    paths = set(helper.source_paths())
    paths.update('candidates/qwen2_resident_matrix/ffn_public/' + name + '.py'
                 for name in ('check_prefix_numeric', 'prefix_execution', 'prefix_owners', 'prefix_arithmetic'))
    paths.update(('scripts/qwen2_block_recipe_model.py', 'src/heteronpu/l9_transport_contract.py',
        'chisel/continuous_prefill/scripts/pack_owner_block_fixture.py',
        'chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py'))
    paths.update('chisel/continuous_prefill/src/main/scala/heteronpu/continuous/' + name
                 for name in ('Qwen2Block.scala', 'QwenOwnerProtocol.scala', 'HostBlockCommands.scala',
                              'ElementwiseMemoryEngine.scala', 'Protocol.scala', 'BlockWritebackFence.scala'))
    paths.add('integration/gemmini/EmitHeteroFP32Alu.scala')
    return sorted(paths)


def source_hashes():
    return {p: file_sha(ROOT / p) for p in source_paths()}


@contextmanager
def frozen_exec(hashes):
    """Reject any repository Python code executed outside the frozen closure."""
    state = {'active': True}
    observed = set()
    def audit(event, args):
        if not state['active'] or event != 'exec':
            return
        filename = getattr(args[0], 'co_filename', '')
        if filename.startswith('<'):
            return
        path = Path(filename).resolve()
        if not path.is_relative_to(ROOT):
            return
        if path.is_relative_to(Path(sys.prefix).resolve()) and 'site-packages' in path.parts:
            return
        relative = str(path.relative_to(ROOT))
        require(relative in hashes and file_sha(path) == hashes[relative],
                'unfrozen or changed executed Python source: ' + relative)
        observed.add(relative)
    sys.addaudithook(audit)
    try:
        yield observed
    finally:
        state['active'] = False


def runtime():
    global _runtime, _import_hashes, _imported_python_paths
    if _runtime is None:
        before = source_hashes()
        with frozen_exec(before):
            modules = tuple(importlib.import_module(PREFIX + name) for name in
                ('check_numeric', 'execute_numeric', 'fixture', 'model',
                 'prefix_execution', 'prefix_owners', 'prefix_arithmetic'))
            recipe = importlib.import_module('scripts.qwen2_block_recipe_model')
            # Exercise the metadata-only dynamic imports while the audit is live.
            modules[2].make_qwen2_21_fixture(16)
            modules[6].source_identity()
        require(source_hashes() == before, 'source changed during runtime import')
        imported = modules[0].imported_python_paths((*modules, recipe))
        require(imported <= set(before), 'unfrozen imported Python dependency: ' + str(sorted(imported - set(before))))
        _runtime, _import_hashes = (*modules, recipe), before
        _imported_python_paths = imported
    require(source_hashes() == _import_hashes, 'source changed after runtime import')
    return _runtime


def strict_flags(argv, *, shared):
    expected = ['-std=c++17', '-O2', '-ffp-contract=off', '-fno-fast-math',
                '-frounding-math', '-fPIC', '-shared'] if shared else [
                '-O2', '-std=c++17', '-ffp-contract=off', '-fno-fast-math']
    flags = [word for word in argv[1:] if word.startswith('-') and word != '-o']
    require(flags == expected and argv.count('-o') == 1, 'strict compile flags differ')


def verified_binaries(recipe):
    """Validate old receipts as binary provenance only, never inherited PASS."""
    receipt = ROOT / CACHE / 'summary.json'
    old = json.loads(receipt.read_text())
    compiled = old['compile']
    strict_flags(compiled['argv'], shared=True)
    source_hash = {}
    for relative in NUMERIC_SOURCES:
        digest = file_sha(ROOT / relative)
        require(old['source_sha256'][relative] == digest and
                file_sha(ROOT / CACHE / 'frozen_sources' / relative) == digest,
                'cached arithmetic source mismatch: ' + relative)
        source_hash[relative] = digest
    require(compiled['argv'][8:] == [str(ROOT / CACHE / 'frozen_sources' / p) for p in NUMERIC_SOURCES[:2]] +
            ['-o', str(ROOT / CACHE / 'numeric_recipe.so')],
            'cached compile translation units/output differ')
    library = ROOT / CACHE / 'numeric_recipe.so'
    require(file_sha(library) == compiled['binary_sha256'], 'cached numeric library changed')
    provenance = json.loads((ROOT / RECIPE / 'generated/provenance.json').read_text())
    require(provenance == recipe['source_identity'], 'original oracle provenance differs')
    strict_flags(provenance['compile_command'], shared=False)
    generated = ROOT / RECIPE / 'generated'
    require(provenance['compile_command'][5:] == [str(generated / 'software_recipe.cpp'),
            '-o', str(generated / 'software_recipe')], 'oracle compiler paths changed')
    for relative, digest in provenance['source_sha256'].items():
        require(file_sha(ROOT / relative) == digest, 'original oracle source changed: ' + relative)
    artifacts = {str(library.relative_to(ROOT)): compiled['binary_sha256']}
    for name, key in (('software_recipe.cpp', 'generated_cpp_sha256'),
                      ('block_layout.h', 'generated_header_sha256')):
        path = generated / name
        require(file_sha(path) == provenance[key], 'original oracle artifact changed: ' + name)
        artifacts[str(path.relative_to(ROOT))] = provenance[key]
    for path in (receipt, generated / 'provenance.json'):
        artifacts[str(path.relative_to(ROOT))] = file_sha(path)
    return dict(numeric_compile=compiled, numeric_source_sha256=source_hash,
                original_recipe_provenance=provenance, artifact_sha256=artifacts, compilation_executed=False,
                old_numeric_pass_inherited=False)


def compiler_identity():
    compiler = shutil.which('g++')
    require(compiler is not None, 'ordinary C++ compiler required for post-checkpoint prefix oracle')
    path = Path(compiler).resolve()
    version = subprocess.check_output([str(path), '--version'], text=True, timeout=10).splitlines()[0]
    return dict(path=str(path), sha256=file_sha(path), version=version)


ORACLE_MAIN = r'''
};
int main(int argc,char** argv){try{
  need(argc==4,"usage: prefix_recipe readonly_arena tokens output_directory");
  verifyFloatEnvironment();
  unsigned t=std::stoul(argv[2]);need(t==16||t==128,"prefix M16/M128 required");
  SoftwareRecipe model(t);
  std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
  need(bool(input)&&uint64_t(input.tellg())==WRITABLE_START,"readonly arena length mismatch");
  input.seekg(0);input.read(reinterpret_cast<char*>(model.reference.data()),WRITABLE_START);
  need(bool(input),"short readonly arena read");
  auto dump=[&](const char* name,uint64_t offset,int width){
    size_t count=size_t(t)*width;
    for(size_t i=0;i<count;i++)need(std::isfinite(model.get(offset,i)),"nonfinite prefix output");
    auto path=std::filesystem::path(argv[3])/(std::string(name)+".f32le");
    need(!std::filesystem::exists(path),"refuse output overwrite");
    std::ofstream output(path,std::ios::binary);
    output.write(reinterpret_cast<const char*>(model.reference.data()+offset/4),count*4);
    need(bool(output),"short prefix output write");
    std::cout<<"PREFIX_ORACLE_STAGE name="<<name<<" values="<<count<<std::endl;
  };
  model.norm(OFF_X,OFF_GAMMA0,OFF_N0);dump("n0",OFF_N0,H);
  // The verbatim original dense method, with its default bias=-1, exposes
  // the raw dot product. Apply the same source add(sum,bias) after export.
  auto projection=[&](uint64_t weight,uint64_t out,uint64_t bias,int width,
                      const char* raw,const char* biased){
    model.dense(OFF_N0,weight,out,H,width);dump(raw,out,width);
    for(unsigned row=0;row<t;row++)for(int col=0;col<width;col++){
      size_t index=size_t(row)*width+col;
      model.put(out,index,add(model.get(out,index),model.get(bias,col)));
    }
    dump(biased,out,width);
  };
  projection(OFF_WQ,OFF_QR,OFF_BQ,H,"qraw","qr");
  projection(OFF_WK,OFF_KR,OFF_BK,KV,"kraw","kr");
  projection(OFF_WV,OFF_V,OFF_BV,KV,"vraw","v");
  model.rope(OFF_QR,OFF_Q,HEADS);dump("q",OFF_Q,H);
  model.rope(OFF_KR,OFF_K,KVHEADS);dump("k",OFF_K,KV);
  std::cout<<"PREFIX_ORACLE_COMPLETE tokens="<<t<<" stages=9"<<std::endl;
  return 0;
}catch(const std::exception& e){std::cerr<<"PREFIX_ORACLE_FAIL "<<e.what()<<std::endl;return 1;}}
'''


def oracle_sources(recipe):
    helpers, maths, identity = recipe.extract_sources(ROOT)
    require(maths.count('  void attention()') == 1, 'original prefix extraction boundary changed')
    prefix_maths = maths.split('  void attention()', 1)[0]
    source = helpers + recipe.HOST_PROBES + recipe.DRIVER + prefix_maths + ORACLE_MAIN
    return {'prefix_recipe.cpp': source.encode(),
            'block_layout.h': recipe.header(recipe.make_layout()).encode()}, dict(
                canonical_source_identity=identity, helpers_sha256=sha(helpers.encode()),
                verbatim_prefix_methods_sha256=sha(prefix_maths.encode()),
                modified_method_bodies=False,
                bias_split='Export original bias=-1 dense result, then original FP32 add(sum,bias).')


def input_spec():
    manifest, recipe = checked_json(PAYLOAD), checked_json(RECIPE + '/RESULT.json')
    prepared = checked_json('work/qwen2_fullgraph_dataflow_20261011/PREPARED.json')
    saved = checked_json(SAVED + '/RESULT.json')
    require((manifest['model_id'], manifest['revision'], manifest['layer_id']) == (MODEL, REVISION, 0),
            'official model/revision/layer mismatch')
    original = recipe['input']
    require(recipe['checkpoint_manifest_sha256'] == PINS[PAYLOAD] and
            recipe['shape']['tokens'] == 128 and recipe['shape']['max_tokens'] == 128 and
            original['token_ids'] == original['positions'] == list(range(128)) and
            original['intermediate_preloads'] == 0 and original['rope_theta'] == 1000000.0 and
            original['rope_table_recipe'] == 'canonical_cpp_initialize_double_libm_then_FP32',
            'original frozen cold M128 input recipe differs')
    require(prepared['arena']['sha256'] == original['readonly_sha256'] == saved['arena_sha256'] and
            saved['prepared_sha256'] == PINS['work/qwen2_fullgraph_dataflow_20261011/PREPARED.json'],
            'frozen input to saved-stage provenance mismatch')
    payloads = {}
    for role, (name, shape) in TENSORS.items():
        matches = [t for t in manifest['tensors'] if t['local_name'] == name]
        require(len(matches) == 1, 'missing/duplicate official tensor: ' + name)
        t = matches[0]
        require(t['dtype'] == 'BF16' and t['shape'] == shape and
                t['bytes'] == math.prod(shape) * 2 and Path(t['file']).name == t['file'],
                'official tensor shape/dtype/path mismatch: ' + name)
        if role == 'embeddings':
            require(t['source_rows'] == [0, 256] and t['source_shape'] == [151936, 1536],
                    'original embedding row slice differs')
        payloads[role] = dict(path=str(Path(PAYLOAD).parent / t['file']), bytes=t['bytes'],
                              sha256=t['sha256'], shape=shape)
    comparisons = {}
    for phase, (name, width) in enumerate(zip(STAGES, WIDTHS)):
        entry = saved['stages'][phase]
        require((entry['phase'], entry['name'], entry['width'], entry['path']) ==
                (phase, name, width, 'phase_%d_%s_recipe.f32le' % (phase, name)), 'saved prefix stage mismatch')
        comparisons[name] = dict(path=SAVED + '/' + entry['path'], sha256=entry['sha256'],
                                 bytes=128 * width * 4, width=width)
    return dict(model=MODEL, revision=REVISION, layer=0, original_input=original,
        metadata_sha256=PINS, payloads=payloads, comparison_only=comparisons,
        oracle_arena=dict(path=RECIPE + '/readonly_arena.f32le', bytes=original['readonly_bytes'],
                          sha256=original['readonly_sha256'])), recipe


def bytes_provider(raw):
    require(isinstance(raw, bytes) and len(raw) % 64 == 0, 'readonly provider extent')
    def read(offset):
        require(type(offset) is int and offset % 64 == 0 and 0 <= offset < len(raw), 'readonly provider bounds')
        return raw[offset:offset + 64]
    return read


def fp32_from_bf16(raw):
    import numpy as np
    words = np.frombuffer(raw, dtype='<u2').astype('<u4') << 16
    require(bool(np.isfinite(words.view('<f4')).all()), 'nonfinite original BF16 input')
    return words.tobytes()


def transpose_bf16(raw, shape):
    import numpy as np
    require(len(raw) == math.prod(shape) * 2 and len(shape) == 2, 'BF16 transpose shape')
    return np.frombuffer(raw, dtype='<u2').reshape(shape).T.copy().tobytes()


def rope_bytes(rows, max_tokens=1024):
    import numpy as np
    require(rows in (16, 128) and max_tokens == 1024, 'public trig layout differs')
    tables = np.zeros((2, max_tokens, 64), dtype='<f4')
    for t in range(rows):
        for j in range(64):
            angle = t / math.pow(1000000.0, 2.0 * j / 128)
            tables[0, t, j], tables[1, t, j] = math.cos(angle), math.sin(angle)
    return tables.tobytes()


def load_inputs(spec, rows, directory=None):
    """Read only raw official inputs, never an intermediate producer export."""
    import numpy as np
    require(rows in (16, 128), 'prefix rows must be M16 or M128')
    raw = {}
    for role, entry in spec['payloads'].items():
        path = ROOT / entry['path'] if directory is None else Path(directory) / (role + '.bf16le')
        data = path.read_bytes()
        require(len(data) == entry['bytes'] and sha(data) == entry['sha256'], 'official payload changed: ' + role)
        raw[role] = data
    embeddings = np.frombuffer(fp32_from_bf16(raw['embeddings']), dtype='<u4').reshape(256, 1536)
    frozen_x = embeddings[spec['original_input']['token_ids']].copy().tobytes()
    require(sha(frozen_x) == spec['original_input']['input_x_sha256'], 'original frozen M128 raw x mismatch')
    inputs = {'x': frozen_x[:rows * 1536 * 4], 'rope': rope_bytes(rows)}
    for role in ('gamma0', 'bq', 'bk', 'bv'):
        inputs[role] = fp32_from_bf16(raw[role])
    for role in ('wq', 'wk', 'wv'):
        inputs[role] = transpose_bf16(raw[role], spec['payloads'][role]['shape'])
    return inputs, raw


class ReferenceGate:
    def __init__(self, spec):
        self.paths = {(ROOT / entry['path']).resolve() for entry in spec['comparison_only'].values()}
        self.paths.update((ROOT / SAVED / ('phase_%d_%s_recipe.f32le' % (i, n))).resolve()
            for i, n in enumerate((*STAGES, 'att', 'o', 'r', 'n1', 'gate', 'up', 'act', 'down', 'y')))
        self.opened, self.active = False, True

    def audit(self, event, args):
        if not self.active or self.opened:
            return
        if event == 'open' and isinstance(args[0], (str, bytes)):
            filename = args[0].decode() if isinstance(args[0], bytes) else args[0]
            path = Path(filename).resolve()
            historical_stage = path.is_relative_to(ROOT / 'work') and path.match('phase_*_recipe.f32le')
            require(path not in self.paths and not historical_stage,
                    'saved comparison accessed before prefix checkpoint')
        if event == 'subprocess.Popen':
            argv = args[1]
            require(not any(Path(str(a)).name in ('software_recipe', 'prefix_recipe') for a in argv),
                    'independent oracle executed before prefix checkpoint')

    def library(self, library):
        gate = self
        class Guarded:
            def __getattr__(self, name):
                require(gate.opened or name not in ('fw_reference', 'sf_reference', 'td_reference'),
                        'reference arithmetic accessed before prefix checkpoint')
                return getattr(library, name)
        return Guarded()


@contextmanager
def reference_gate(spec):
    gate = ReferenceGate(spec)
    sys.addaudithook(gate.audit)
    try:
        yield gate
    finally:
        gate.active = False


def identities(inputs):
    return {name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in inputs.items()}


def prepare(out, rows=16, epoch=7):
    """Freeze reviewed sources and original raw inputs; execute no arithmetic."""
    out = Path(out).resolve()
    require(not out.exists(), 'use a new prefix snapshot directory')
    helper, _, fixtures, _, _, _, _, recipe_module = runtime()
    spec, recipe = input_spec()
    binaries = verified_binaries(recipe)
    before = source_hashes()
    with frozen_exec(before), reference_gate(spec):
        oracle, oracle_identity = oracle_sources(recipe_module)
        compiler = compiler_identity()
        fixture = fixtures.make_qwen2_21_fixture(rows, epoch)
        metadata = helper.metadata_identity(fixture)
        inputs, raw = load_inputs(spec, rows)
        require(all(len(data) == fixture.allocations[name].storage_bytes for name, data in inputs.items()),
                'readonly input extent differs from public fixture')
        out.mkdir(parents=True)
        for relative, digest in before.items():
            data = (ROOT / relative).read_bytes()
            require(sha(data) == digest, 'source changed during freeze: ' + relative)
            target = out / 'frozen_sources' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (out / 'frozen_inputs').mkdir()
        (out / 'frozen_oracle').mkdir()
        for name, data in oracle.items():
            (out / 'frozen_oracle' / name).write_bytes(data)
        for role, data in raw.items():
            (out / 'frozen_inputs' / (role + '.bf16le')).write_bytes(data)
        for name in ('command', 'descriptor'):
            table = getattr(fixture.config, name)
            (out / (name + '_table.bin')).write_bytes(fixture.memory.mappings[table.base])
        require(before == source_hashes(), 'source changed during prefix preparation')
        snapshot = dict(schema=1, status='PREPARED_PREFIX_NOT_EXECUTED', rows=rows, epoch=epoch,
            source_sha256=before, source_manifest_sha256=sha(encoded(before)),
            imported_python_sha256={name: before[name] for name in sorted(_imported_python_paths)},
            source_identity='New public21 prefix closure; no old public FFN4 PASS inherited.',
            host_tool_identity=helper.host_tool_identity(), metadata=metadata, input_spec=spec,
            loaded_inputs=identities(inputs), binaries=binaries, public_execution_executed=False,
            oracle_source_sha256={name: sha(raw) for name, raw in oracle.items()},
            oracle_identity=oracle_identity, oracle_compiler=compiler,
            compilation_executed=False, saved_stage_payloads_read=False,
            native_acceptance='NOT_NATIVE_ACCEPTED', official_framework_forward=False,
            initial_inputs='Original frozen cold M128 token IDs; M16 uses its first 16 rows.',
            trig_layout=dict(public_max_tokens=1024, canonical_max_tokens=128,
                sine_half_offset_bytes=1024 * 64 * 4, active_rows=rows,
                recipe='double math.pow/cos/sin then one FP32 rounding; inactive rows zero'))
        path = out / 'SNAPSHOT.json'
        path.write_bytes(encoded(snapshot))
        return path, snapshot


def verify_snapshot(path, digest):
    path = Path(path).resolve()
    require(isinstance(digest, str) and len(digest) == 64 and file_sha(path) == digest,
            'reviewed prefix SNAPSHOT.json SHA-256 differs')
    snapshot = json.loads(path.read_text())
    require(snapshot['status'] == 'PREPARED_PREFIX_NOT_EXECUTED' and
            snapshot['source_manifest_sha256'] == sha(encoded(snapshot['source_sha256'])) and
            not snapshot['public_execution_executed'] and not snapshot['compilation_executed'] and
            not snapshot['saved_stage_payloads_read'], 'prefix snapshot is not fresh preparation')
    require(source_hashes() == snapshot['source_sha256'], 'live prefix sources differ from snapshot')
    for relative, expected in snapshot['source_sha256'].items():
        require(file_sha(path.parent / 'frozen_sources' / relative) == expected, 'frozen source changed: ' + relative)
    for name, expected in snapshot['oracle_source_sha256'].items():
        require(file_sha(path.parent / 'frozen_oracle' / name) == expected, 'frozen prefix oracle changed: ' + name)
    require(compiler_identity() == snapshot['oracle_compiler'], 'prefix oracle compiler changed')
    spec, recipe = input_spec()
    require(spec == snapshot['input_spec'] and verified_binaries(recipe) == snapshot['binaries'],
            'original input/binary identity changed since freeze')
    return snapshot


def configure_library(path):
    library = C.CDLL(str(path))
    u16, u32 = C.POINTER(C.c_uint16), C.POINTER(C.c_uint32)
    for name, args in (('td_reset', []), ('td_group', [C.c_uint] * 3),
        ('td_step', [C.c_uint] * 6 + [u16, u16, u32]), ('td_seed_begin', [C.c_uint]),
        ('td_seed_beat', [C.c_uint, C.c_uint, u32]), ('td_seed_commit', [C.c_uint])):
        getattr(library, name).argtypes, getattr(library, name).restype = args, C.c_int
    require(library.td_reset() == 0, 'initial arithmetic reset failed')
    return library


def validate_checkpoint(x, memory, evidence):
    host, owner = x.host, x.owner
    require(host.pc == host.completed == host.jobs == 10 and host.state == 'decode' and
            host.result is None and host.status is None and x.launch_result is None and
            owner.state == x.prefix_owner.state == 'idle' and not x.reset_required() and
            owner.lease is None and not owner.tiles.leased and memory.pending is None,
            'prefix checkpoint not quiescent after ten completions')
    require([c['pc'] for c in x.completions] == list(range(10)) and
            all(c['status'] is None for c in x.completions) and
            x.counts['completion_fire'] == x.counts['owner_result_fire'] == 10 and
            x.counts['result_fire'] == 0, 'public prefix completion fence incomplete')
    report = memory.report()
    require({n for n, r in report['outputs'].items() if r['published']} == set(OUTPUTS),
            'unexpected prefix outputs published')
    for name in OUTPUTS:
        r = report['outputs'][name]
        require(r['terminal'] and r['bytes'] == r['written_bytes'] == r['ack_bytes'],
                'physical final ACK/terminal missing: ' + name)
    require(len(evidence['reports']) == 10, 'missing actual prefix job report')
    for item in evidence['reports']:
        r = item['report']
        if item['kind'] == 'Dense':
            fence = r['final_ack_fence']
            require(fence['held_ticks'] > 0 and fence['final_ack_tick'] < fence['terminal_tick'],
                    'Dense final ACK fence missing')
        else:
            require(r['accepted']['final_ack_stall'] > 0, 'prefix final ACK backpressure missing')
    return dict(public_completion_pcs=list(range(10)), all_actual_final_acks_before_comparison=True,
                pc10_not_executed=True, launch_terminal_observed=False,
                same_owner_and_banks=x.bank_ids == (id(owner), id(owner.a_banks), id(owner.b_banks), id(owner.tiles.banks)))


def compare_after_checkpoint(snapshot, snapshot_path, actual, out, deadline, gate):
    """Two independent comparisons; no oracle tensor is an execution input."""
    import numpy as np
    require(gate.opened, 'comparison requires validated prefix checkpoint')
    rows, spec = snapshot['rows'], snapshot['input_spec']
    arena = spec['oracle_arena']
    arena_path = ROOT / arena['path']
    require(arena_path.stat().st_size == arena['bytes'] and file_sha(arena_path) == arena['sha256'],
            'original readonly oracle arena changed')
    target = Path(out) / 'independent_original_recipe'
    target.mkdir()
    timeout = min(600, deadline - time.monotonic())
    require(timeout > 0, 'no remaining independent comparison budget')
    frozen = Path(snapshot_path).parent / 'frozen_oracle'
    for name, digest in snapshot['oracle_source_sha256'].items():
        require(file_sha(frozen / name) == digest, 'frozen oracle source changed before compile')
    executable = target / 'prefix_recipe'
    command = [snapshot['oracle_compiler']['path'], '-O2', '-std=c++17', '-ffp-contract=off',
               '-fno-fast-math', '-frounding-math', str(frozen / 'prefix_recipe.cpp'), '-o', str(executable)]
    with (target / 'compile.log').open('w') as log:
        build = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=min(30, timeout))
    require(build.returncode == 0, 'independent prefix oracle compile failed')
    compiled = dict(argv=command, binary_sha256=file_sha(executable),
                    source_sha256=snapshot['oracle_source_sha256'], compiler=snapshot['oracle_compiler'])
    require(compiler_identity() == snapshot['oracle_compiler'], 'oracle compiler changed during comparison')
    for name, digest in snapshot['oracle_source_sha256'].items():
        require(file_sha(frozen / name) == digest, 'frozen oracle source changed during compile')
    (target / 'compile_receipt.json').write_bytes(encoded(compiled))
    timeout = min(600, deadline - time.monotonic())
    require(timeout > 0, 'no remaining independent oracle budget')
    argv = [str(executable), str(arena_path), str(rows), str(target)]
    with (target / 'run.log').open('w') as log:
        run = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    log = (target / 'run.log').read_text()
    require(run.returncode == 0 and log.count('SOFTWARE_FLOAT_ENV ') == 1 and
            log.count('PREFIX_ORACLE_STAGE ') == 9 and 'PREFIX_ORACLE_COMPLETE ' in log,
            'independent original ordered C++ prefix recipe incomplete')
    require(file_sha(arena_path) == arena['sha256'], 'oracle input arena changed during comparison')
    require(file_sha(executable) == compiled['binary_sha256'], 'oracle executable changed during comparison')
    direct, saved, result = {}, {}, {}
    for phase, name in enumerate(STAGES):
        entry = spec['comparison_only'][name]
        gold = (ROOT / entry['path']).read_bytes()
        require(len(gold) == entry['bytes'] and sha(gold) == entry['sha256'], 'saved producer changed: ' + name)
        saved[name] = gold[:rows * entry['width'] * 4]
    for name in OUTPUTS[:-1]:
        direct[name] = (target / (name + '.f32le')).read_bytes()
    direct['kv'], saved['kv'] = direct['k'] + direct['v'], saved['k'] + saved['v']
    for name in OUTPUTS:
        a, d = actual[name], direct[name]
        require(len(a) == len(d), 'independent output extent differs: ' + name)
        words = [np.frombuffer(raw, dtype='<u4') for raw in (a, d)]
        result[name] = dict(values=len(a) // 4, actual_sha256=sha(a), independent_sha256=sha(d),
            independent_bit_mismatches=int(np.count_nonzero(words[0] != words[1])), saved_bit_mismatches=None)
        if name in saved:
            s = saved[name]
            require(len(a) == len(s), 'saved output extent differs: ' + name)
            result[name].update(saved_sha256=sha(s),
                saved_bit_mismatches=int(np.count_nonzero(words[0] != np.frombuffer(s, dtype='<u4'))))
    return dict(outputs=result, oracle_argv=argv, oracle_compile=compiled, oracle_recipe_stages_computed=9,
                actual_public_pcs_executed=list(range(10)),
                saved_scope='Six saved prefix stages plus packed KV derived from saved k and v; no saved att comparison.')


def verify_m16(path, digest, snapshot):
    require(path is not None and digest is not None and file_sha(path) == digest,
            'M128 requires the completed M16 summary and its SHA-256')
    prior = json.loads(Path(path).read_text())
    require(prior['status'] == 'PASS_PUBLIC21_PREFIX_SOFTWARE_ONLY_NOT_NATIVE_ACCEPTED' and prior['rows'] == 16 and
            prior['native_acceptance'] == 'NOT_NATIVE_ACCEPTED' and
            prior['source_sha256'] == snapshot['source_sha256'] and
            prior['source_sha256_after'] == snapshot['source_sha256'] and
            prior['input_spec'] == snapshot['input_spec'] and prior['binaries'] == snapshot['binaries'],
            'M16 prerequisite scope/source differs')
    outputs, gate = prior['comparison']['outputs'], prior['comparison_gate']
    require(set(outputs) == set(OUTPUTS), 'M16 prerequisite exact output set differs')
    widths = dict.fromkeys(('n0', 'qraw', 'qr', 'q'), 1536)
    widths.update(dict.fromkeys(('kraw', 'kr', 'k', 'vraw', 'v'), 256))
    widths['kv'] = 512
    for name in OUTPUTS:
        item = outputs[name]
        actual = item.get('actual_sha256')
        require(type(item.get('values')) is int and item['values'] == 16 * widths[name] and
                isinstance(actual, str) and len(actual) == 64 and
                all(letter in '0123456789abcdef' for letter in actual) and
                item.get('independent_sha256') == actual and
                type(item.get('independent_bit_mismatches')) is int and item['independent_bit_mismatches'] == 0,
                'M16 prerequisite independent output evidence differs: ' + name)
        if name in (*STAGES, 'kv'):
            require(type(item.get('saved_bit_mismatches')) is int and item['saved_bit_mismatches'] == 0 and
                    item.get('saved_sha256') == actual, 'M16 prerequisite saved evidence differs: ' + name)
        else:
            require('saved_bit_mismatches' in item and item['saved_bit_mismatches'] is None and
                    'saved_sha256' not in item, 'M16 raw output must not claim a saved comparison: ' + name)
    require(gate.get('public_completion_pcs') == list(range(10)) and
            gate.get('all_actual_final_acks_before_comparison') is True and
            gate.get('pc10_not_executed') is True and gate.get('launch_terminal_observed') is False and
            gate.get('same_owner_and_banks') is True and
            prior['comparison'].get('actual_public_pcs_executed') == list(range(10)),
            'M16 prerequisite checkpoint evidence differs')
    host = prior['execution']['host']
    require([entry['pc'] for entry in host['completions']] == list(range(10)) and
            all(entry['status'] is None for entry in host['completions']) and
            host['launch_result'] is None and host['reset_required'] is False and
            host.get('same_owner_and_banks') is True and
            host['accepted'].get('completion_fire') == host['accepted'].get('owner_result_fire') == 10 and
            host['accepted'].get('result_fire') == 0,
            'M16 prerequisite retained public completion evidence differs')
    return dict(path=str(Path(path).resolve()), sha256=digest)


def run(out, snapshot_path, snapshot_sha256, wall_budget=900, m16_prerequisite=None, m16_sha256=None):
    out, snapshot_path = Path(out).resolve(), Path(snapshot_path).resolve()
    require(not out.exists() and wall_budget > 0, 'new output directory and positive wall budget required')
    snapshot = verify_snapshot(snapshot_path, snapshot_sha256)
    helper, execution, fixtures, public, prefix, owners, _, _ = runtime()
    require(_import_hashes == snapshot['source_sha256'] and
            helper.host_tool_identity() == snapshot['host_tool_identity'], 'runtime tooling/import identity differs')
    require({name: _import_hashes[name] for name in sorted(_imported_python_paths)} ==
            snapshot['imported_python_sha256'], 'executed Python import closure differs from snapshot')
    prerequisite = verify_m16(m16_prerequisite, m16_sha256, snapshot) if snapshot['rows'] == 128 else None
    rows, started, cpu = snapshot['rows'], time.monotonic(), time.process_time()
    deadline = started + wall_budget
    out.mkdir(parents=True)
    report = dict(status='PINNED_BEFORE_EXECUTION', rows=rows, epoch=snapshot['epoch'],
        reviewed_snapshot=str(snapshot_path), reviewed_snapshot_sha256=snapshot_sha256,
        source_sha256=snapshot['source_sha256'], input_spec=snapshot['input_spec'], binaries=snapshot['binaries'],
        host_tool_identity=snapshot['host_tool_identity'], m16_prerequisite=prerequisite,
        scope='PUBLIC21_PC0_9_ONE_PHYSICAL_MAP_SOFTWARE_MODEL',
        native_acceptance='NOT_NATIVE_ACCEPTED', native_policy='UNCHANGED_FAIL_POLICY_PENDING',
        rtl_executed=False, hardware_arithmetic_executed=False, arithmetic_library_compilation_executed=False,
        actual_idma=False, full_block_executed=False, attention_suffix_executed=False,
        official_framework_forward=False, hardware_cycles=None, full_wall_mac_utilization=None,
        protocol_model_ticks_are_hardware_cycles=False, old_public_ffn4_pass_inherited=False)
    def save():
        (out / 'summary.json').write_bytes(encoded(report))
    try:
        require(sys.byteorder == 'little', 'little-endian host required')
        with frozen_exec(snapshot['source_sha256']) as observed, reference_gate(snapshot['input_spec']) as gate:
            fixture = fixtures.make_qwen2_21_fixture(rows, snapshot['epoch'])
            require(helper.metadata_identity(fixture) == snapshot['metadata'], 'public21 metadata changed')
            for name, table in snapshot['metadata']['tables'].items():
                data = (snapshot_path.parent / (name + '_table.bin')).read_bytes()
                require(sha(data) == table['sha256'], 'frozen public metadata changed')
                (out / (name + '_table.bin')).write_bytes(data)
            inputs, _ = load_inputs(snapshot['input_spec'], rows, snapshot_path.parent / 'frozen_inputs')
            require(identities(inputs) == snapshot['loaded_inputs'], 'frozen initial numeric inputs differ')
            memory = prefix.PhysicalMemory(fixture, {name: bytes_provider(raw) for name, raw in inputs.items()})
            region = fixture.config.regions[3]
            numeric = execution.numeric
            owner = numeric.model.FfnDrainOwnerModel(numeric.model.PrefixWorkspace(region.base,
                region.limit - region.base, fixture.config.epoch + 1, 2560),
                enable_ffn_window=True, enable_ffn_tiles=True, enable_ffn_drain=True)
            frontend = public.PublicFrontend(memory.metadata_port(), fixture.config)
            x = execution.PublicExecution(frontend, owner, numeric.CappedTrace(), deadline,
                host=public.group.HostControl(enabled=True, legacy_prefix=True), prefix_owner=owners.PrefixOwner())
            report['loaded_inputs'] = identities(inputs)
            report['prelaunch_intermediate_payloads'] = []
            report['metadata'] = snapshot['metadata']
            save()
            (out / 'FROZEN_PINS.json').write_bytes(encoded(report))
            library = configure_library(ROOT / CACHE / 'numeric_recipe.so')
            evidence = prefix.execute_public_prefix(x, memory, gate.library(library), out)
            report['execution'] = evidence
            report['public_metadata_observations'] = dict(
                accepted_records=frontend.port.trace, command_reads=frontend.command_reads,
                policy_reads=frontend.policy_reads, typed_root_reads=frontend.reader.reads,
                physical_read_bytes=sum(record['physical_bytes'] for record in frontend.port.trace),
                reads_by_allocation=dict(memory.read_regions),
                record_reader_poison=frontend.port.machine.poison,
                shares_numeric_physical_memory=frontend.port.memory is frontend.memory and
                    frontend.memory.physical_memory is memory,
                model_ticks_are_hardware_cycles=False)
            report['comparison_gate'] = validate_checkpoint(x, memory, evidence)
            require(report['comparison_gate']['same_owner_and_banks'], 'owner or banks replaced')
            require(source_hashes() == snapshot['source_sha256'], 'source drift during actual prefix execution')
            actual = {name: memory.raw(fixture.allocations[name].address, fixture.allocations[name].storage_bytes)
                      for name in OUTPUTS}
            for name, raw in actual.items():
                (out / ('actual_' + name + '.f32le')).write_bytes(raw)
            report['status'] = 'PREFIX_CHECKPOINT_COMPARISON_PENDING'
            save()
            gate.opened = True
            report['comparison'] = compare_after_checkpoint(snapshot, snapshot_path, actual, out, deadline, gate)
            require(all(v['independent_bit_mismatches'] == 0 and v['saved_bit_mismatches'] in (None, 0)
                        for v in report['comparison']['outputs'].values()), 'prefix differs from original ordered/saved recipe')
            report['source_sha256_after'] = source_hashes()
            require(report['source_sha256_after'] == snapshot['source_sha256'], 'source drift during comparison')
            require(verified_binaries(checked_json(RECIPE + '/RESULT.json')) == snapshot['binaries'],
                    'arithmetic/oracle binary provenance changed during run')
            require(identities(inputs) == snapshot['loaded_inputs'], 'initial readonly input mutation')
            require(helper.imported_python_paths(_runtime) <= set(snapshot['source_sha256']),
                    'late unfrozen repository Python import')
            report.update(status='PASS_PUBLIC21_PREFIX_SOFTWARE_ONLY_NOT_NATIVE_ACCEPTED',
                executed_imports_observed=sorted(observed), host_wall_seconds=time.monotonic() - started,
                host_cpu_seconds=time.process_time() - cpu,
                host_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            save()
            return report
    except Exception as error:
        report.update(status='FAILED', error=str(error), host_wall_seconds=time.monotonic() - started)
        if 'memory' in locals():
            report['failed_memory'] = memory.report()
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--rows', type=int, choices=(16, 128), default=16)
    parser.add_argument('--epoch', type=int, default=7)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--expected-snapshot-sha256')
    parser.add_argument('--wall-budget', type=int, default=900)
    parser.add_argument('--m16-prerequisite', type=Path)
    parser.add_argument('--m16-sha256')
    args = parser.parse_args()
    if args.prepare_only:
        require(args.snapshot is None and args.expected_snapshot_sha256 is None, 'prepare does not accept snapshot')
        path, result = prepare(args.out, args.rows, args.epoch)
        print(json.dumps(dict(status=result['status'], path=str(path), sha256=file_sha(path))))
    else:
        require(args.snapshot is not None and args.expected_snapshot_sha256 is not None, 'execution requires reviewed snapshot')
        result = run(args.out, args.snapshot, args.expected_snapshot_sha256, args.wall_budget,
                     args.m16_prerequisite, args.m16_sha256)
        print(json.dumps({k: result[k] for k in ('status', 'rows', 'host_wall_seconds')}))
