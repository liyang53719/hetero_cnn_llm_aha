#!/usr/bin/env python3
"""Run the committed Qwen2 L0 arithmetic recipe entirely in ordinary C++.

This is a software numerical model, not an RTL simulation, timing result, or
hardware correctness claim. The generated layout is a checked Python mirror of
QwenBlockLayout, not Chisel output. Every consumer uses this model's own previous
stage output. Checkpoint or official-forward intermediates are never injected.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import numpy as np

SOURCE = 'chisel/continuous_prefill/tests/qwen2_block.cpp'
LAYOUT_SOURCE = 'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala'
SHAPE = dict(hidden=1536, ffn=8960, heads=12, kv_heads=2, head_dim=128, max_tokens=128)
STAGE_NAMES = ('n0', 'qr', 'kr', 'v', 'q', 'k', 'att', 'o', 'r', 'n1', 'gate', 'up', 'act', 'down', 'y')
# Guard the exact bounded source sections. Changes require an intentional review
# and test update; silently accepting changed oracle arithmetic is forbidden.
SECTION_SHA256 = {
    'helpers': 'd1890cd7d8e2d3bc0af780d35c7a1f1fcf9f6e0c59fa655178c427bb93f1e15b',
    'math': '4507a74bffa481584038713e2bc7de4c675d291176fc22a5c4c2a10fba732ee8',
    'layout': 'c30d7484172db263712900cc2d43b2962227ae16266e0085eca7d156bbd4396f',
}
# DEFAULT-OFF witness for the reviewed immutable public source export. These
# constants are source-closure pins, never caller-supplied trust anchors.
COMMITTED_WITNESS_MANIFEST_SHA256 = '0652c9a94fc1e3498ed925e0f73116634a2c2f73fcc81eb7dc2211fdd5305286'
COMMITTED_WITNESS_IDENTITY = {
    'commit': '9a639053f797b19fba5b6d9cfe830dc8c3009730',
    'tree': '78752201929029bc6b084d5e89ae82ec8c7e1575',
    'path': SOURCE,
    'mode': '100644',
    'bytes': 23995,
    'sha256': 'd757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5',
    'git_blob': 'e40538df77611f10e39e70d5520397886a5607c8',
    'readback': 'exact immutable commit GitHub contents UTF8 bytes; SHA1 blob equals full reconstructed tree entry',
    'assembled_sha256_claim': 'd757e1271210e260ca320cddf4175c306d3cf52835ea45f20ca9dfb56ac34db5',
    'assembled_byte_equal': True,
    'checked_utc': '2026-10-25T04:33:07.737499+00:00',
    'native_execution_or_frozen_repo_mutation': False,
}
FLAGS = ['-O2', '-std=c++17', '-ffp-contract=off', '-fno-fast-math']
WEIGHTS = {
    'wq': ('self_attn.q_proj.weight', 'hidden', 'hidden'),
    'wk': ('self_attn.k_proj.weight', 'kv', 'hidden'),
    'wv': ('self_attn.v_proj.weight', 'kv', 'hidden'),
    'wo': ('self_attn.o_proj.weight', 'hidden', 'hidden'),
    'wg': ('mlp.gate_proj.weight', 'ffn', 'hidden'),
    'wu': ('mlp.up_proj.weight', 'ffn', 'hidden'),
    'wd': ('mlp.down_proj.weight', 'hidden', 'ffn'),
}
VECTORS = {'gamma0': 'input_layernorm.weight', 'gamma1': 'post_attention_layernorm.weight',
           'bq': 'self_attn.q_proj.bias', 'bk': 'self_attn.k_proj.bias', 'bv': 'self_attn.v_proj.bias'}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 << 20), b''):
            h.update(data)
    return h.hexdigest()


def section(text: str, begin: str, end: str) -> str:
    require(text.count(begin) == text.count(end) == 1, 'source extraction boundary absent or ambiguous')
    first, last = text.index(begin), text.index(end)
    require(first < last, 'source extraction boundary order')
    return text[first:last]


def _read_committed_source_witness(witness_path: Path, manifest_path: Path) -> tuple[str, dict]:
    """Validate exact exported bytes; no Git, subprocess, or identity injection."""
    manifest_raw = Path(manifest_path).read_bytes()
    require(sha(manifest_raw) == COMMITTED_WITNESS_MANIFEST_SHA256,
            'committed witness manifest changed; explicit review required')
    manifest = json.loads(manifest_raw.decode('utf-8'))
    require(type(manifest) is dict and set(manifest) == set(COMMITTED_WITNESS_IDENTITY)
            and all(type(manifest[key]) is type(value) and manifest[key] == value
                    for key, value in COMMITTED_WITNESS_IDENTITY.items()),
            'committed witness manifest schema or fixed identity mismatch')
    raw = Path(witness_path).read_bytes()
    require(len(raw) == manifest['bytes'] and sha(raw) == manifest['sha256'],
            'committed witness byte count or SHA256 mismatch')
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
    require(blob == manifest['git_blob'], 'committed witness Git blob mismatch')
    return raw.decode('utf-8'), dict(manifest, manifest_sha256=sha(manifest_raw))


def extract_sources(root: Path, *, committed_source_witness: Path | None = None,
                    committed_source_manifest: Path | None = None) -> tuple[str, str, dict]:
    require((committed_source_witness is None) == (committed_source_manifest is None),
            'committed witness and manifest must be supplied together')
    original = (root / SOURCE).read_text()
    layout_source = (root / LAYOUT_SOURCE).read_text()
    fragments = {
        'helpers': section(original, '#include "block_layout.h"', 'struct Pending'),
        'math': section(original, '  void norm(', '  void compareStage('),
        'layout': section(layout_source, 'class QwenBlockLayout(', 'class BlockLaunch '),
    }
    for name, fragment in fragments.items():
        require(sha(fragment.encode()) == SECTION_SHA256[name], f'canonical {name} section changed; explicit review required')
    # Pin the arithmetic to a committed source, even in a dirty working tree.
    witness_identity = None
    if committed_source_witness is None:
        committed = subprocess.run(['git', 'show', 'HEAD:' + SOURCE], cwd=root, check=True,
                                   capture_output=True, text=True, timeout=15).stdout
    else:
        committed, witness_identity = _read_committed_source_witness(
            committed_source_witness, committed_source_manifest)
        require(sha((root / SOURCE).read_bytes()) == witness_identity['sha256'],
                'working source differs from reviewed committed witness')
    require(section(committed, '#include "block_layout.h"', 'struct Pending') == fragments['helpers']
            and section(committed, '  void norm(', '  void compareStage(') == fragments['math'],
            'recipe arithmetic is not identical to committed HEAD')
    identity = {
        'source_sha256': {SOURCE: sha(original.encode()), LAYOUT_SOURCE: sha(layout_source.encode())},
        'committed_cpp_sha256': sha(committed.encode()),
        'section_sha256': {name: sha(text.encode()) for name, text in fragments.items()},
        'git_head': (subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, check=True,
                                    capture_output=True, text=True, timeout=15).stdout.strip()
                     if witness_identity is None else None),
    }
    if witness_identity is not None:
        identity.update(committed_source_resolution='reviewed-immutable-export-v1',
                        committed_source_commit=witness_identity['commit'],
                        committed_source_tree=witness_identity['tree'],
                        committed_source_blob=witness_identity['git_blob'],
                        committed_source_witness=witness_identity)
    return fragments['helpers'], fragments['math'], identity


def make_layout(shape: dict | None = None) -> dict:
    """Mirror the hash-guarded QwenBlockLayout; small shapes are test-only."""
    s = dict(SHAPE if shape is None else shape)
    h, f, heads, kv_heads, hd, mt = (int(s[k]) for k in SHAPE)
    require(h == heads * hd and heads % kv_heads == 0, 'invalid head shape')
    require(h % 16 == f % 16 == 0 and hd >= 32 and hd % 32 == 0 and 0 < mt <= 128, 'invalid model shape')
    kv = kv_heads * hd
    cursor = 0
    regions = []
    def add(name: str, words: int, external: bool) -> None:
        nonlocal cursor
        cursor = (cursor + 63) & -64
        regions.append(dict(name=name, offset=cursor, words=words, external=external))
        cursor += words * 4
    for name, k, n in [('wq',h,h),('wk',h,kv),('wv',h,kv),('wo',h,h),('wg',h,f),('wu',h,f),('wd',f,h)]:
        add(name, k*n, True)
    for name in ('gamma0','gamma1','bq'):
        add(name, h, True)
    for name in ('bk','bv'):
        add(name, kv, True)
    add('cos', mt*hd//2, True)
    add('sin', mt*hd//2, True)
    add('x', mt*h, True)
    writable_start = (cursor+63)&-64
    widths = (h,h,kv,kv,h,kv,h,h,h,h,f,f,f,h,h)
    for name, width in zip(STAGE_NAMES, widths):
        add(name, mt*width, False)
    return dict(**s, regions=regions, writable_start=writable_start,
                arena_bytes=(cursor+63)&-64, layout_kind='software_mirror_of_hash_guarded_QwenBlockLayout',
                generated_by_chisel=False)


def logical_macs(tokens: int, shape: dict = SHAPE) -> dict:
    h, f = shape['hidden'], shape['ffn']
    kv = shape['kv_heads']*shape['head_dim']
    dense = tokens * (2*h*h + 2*h*kv + 3*h*f)
    attention = shape['heads'] * shape['head_dim'] * tokens * (tokens+1)
    return dict(dense=dense, attention_qk_and_pv=attention, total=dense+attention)


def header(layout: dict) -> str:
    names = {'hidden':'H','ffn':'F','heads':'HEADS','kv_heads':'KVHEADS','head_dim':'HD','max_tokens':'MAX_TOKENS'}
    text = '#pragma once\n#include <cstdint>\n'
    text += ''.join(f'static constexpr int {cpp}={layout[key]};\n' for key,cpp in names.items())
    text += f'static constexpr uint64_t WRITABLE_START={layout["writable_start"]}ULL,ARENA_BYTES={layout["arena_bytes"]}ULL;\n'
    return text + ''.join(f'static constexpr uint64_t OFF_{r["name"].upper()}={r["offset"]}ULL;\n' for r in layout['regions'])


HOST_PROBES = r'''
#if defined(__x86_64__) || defined(__i386__)
#include <xmmintrin.h>
#endif
static void verifyFloatEnvironment(){
  need(std::fesetround(FE_TONEAREST)==0 && std::fegetround()==FE_TONEAREST,"FE_TONEAREST unavailable");
#if defined(__x86_64__) || defined(__i386__)
  unsigned before=_mm_getcsr();_mm_setcsr(before & ~((1u<<15)|(1u<<6)));
  unsigned after=_mm_getcsr();need((after&((1u<<15)|(1u<<6)))==0,"cannot clear FTZ/DAZ");
#endif
  // Volatile operands keep these execution probes out of constant folding.
  volatile float tiny=fp(0x00000001u),one=1.0f,half=0.5f,normal=fp(0x00800000u);
  volatile float pzero=fp(0u),nzero=fp(0x80000000u),minusone=-1.0f;
  volatile float a=fp(0x3f800001u),b=fp(0x3f7ffffeu);
  need(bits(add(tiny,tiny))==2u,"subnormal add probe failed");
  need(bits(mul(tiny,one))==1u,"subnormal multiply probe failed");
  need(bits(mul(normal,half))==0x00400000u,"gradual underflow probe failed");
  need(bits(std::fma(tiny,one,pzero))==1u,"subnormal FMA probe failed");
  need(bits(mul(nzero,one))==0x80000000u && bits(mul(pzero,one))==0u,"signed-zero multiply probe failed");
  need(bits(add(nzero,nzero))==0x80000000u && bits(add(nzero,pzero))==0u,"signed-zero add probe failed");
  need(bits(std::fma(a,b,minusone))==0xa8800000u,"single-round FMA probe failed");
  need(bits(add(mul(a,b),minusone))==0u,"uncontracted multiply-add probe failed");
  std::cout<<"SOFTWARE_FLOAT_ENV rounding=FE_TONEAREST probes=10";
#if defined(__x86_64__) || defined(__i386__)
  std::cout<<" arch=x86 mxcsr_before="<<before<<" mxcsr_after="<<after<<" ftz=0 daz=0";
#else
  std::cout<<" arch=other mxcsr_before=unavailable mxcsr_after=unavailable ftz=probe_verified daz=probe_verified";
#endif
  std::cout<<std::endl;
}
'''

DRIVER = r'''
class SoftwareRecipe {
public:
  std::vector<float> reference; unsigned tokens;
  SoftwareRecipe(unsigned t):reference(ARENA_BYTES/4,fp(0x7fc00001u)),tokens(t){}
  float get(uint64_t offset,size_t i)const{return reference.at(offset/4+i);}
  void put(uint64_t offset,size_t i,float x){reference.at(offset/4+i)=x;}
'''
MAIN = r'''
};
int main(int argc,char** argv){try{
  need(argc==4,"usage: software_recipe readonly_arena tokens output_directory");
  verifyFloatEnvironment();
  need(sizeof(float)==4,"FP32 host required");
  uint32_t endian=1;need(*reinterpret_cast<uint8_t*>(&endian)==1,"little-endian host required");
  unsigned t=std::stoul(argv[2]);need(t>0&&t<=MAX_TOKENS,"token capacity exceeded");
  SoftwareRecipe model(t);
  std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
  need(bool(input)&&uint64_t(input.tellg())==WRITABLE_START,"readonly arena length mismatch");
  input.seekg(0);input.read(reinterpret_cast<char*>(model.reference.data()),WRITABLE_START);
  need(bool(input),"short readonly arena read");
  model.computeReference();
  for(unsigned phase=0;phase<STAGES.size();phase++){
    const auto& s=STAGES[phase];size_t count=size_t(t)*s.width;
    for(size_t i=0;i<count;i++)need(std::isfinite(model.get(s.off,i)),"nonfinite stage output");
    auto path=std::filesystem::path(argv[3])/("phase_"+std::to_string(phase)+"_"+s.name+"_recipe.f32le");
    need(!std::filesystem::exists(path),"refuse output overwrite");
    std::ofstream output(path,std::ios::binary);
    output.write(reinterpret_cast<const char*>(model.reference.data()+s.off/4),count*4);
    need(bool(output),"short stage output write");
    std::cout<<"SOFTWARE_RECIPE_STAGE phase="<<phase<<" name="<<s.name<<" values="<<count<<std::endl;
  }
  std::cout<<"SOFTWARE_RECIPE_COMPLETE tokens="<<t<<" stages=15"<<std::endl;
  return 0;
}catch(const std::exception& e){std::cerr<<"SOFTWARE_RECIPE_FAIL "<<e.what()<<std::endl;return 1;}}
'''


def generate_and_compile(root: Path, output: Path, shape: dict | None = None) -> tuple[dict, dict]:
    require(not output.exists(), 'refuse existing generated directory')
    helpers, maths, provenance = extract_sources(root)
    layout = make_layout(shape)
    text = '// Ordinary C++ software numerical model; not a hardware simulator.\n' + helpers + HOST_PROBES + DRIVER + maths + MAIN
    require(not re.search(r'Verilat|verilat|BlockDut|VQwen|d\.eval|DUT', text), 'hardware/DUT symbol in software model')
    output.mkdir(parents=True)
    (output/'block_layout.h').write_text(header(layout))
    (output/'software_recipe.cpp').write_text(text)
    (output/'layout.json').write_text(json.dumps(layout, indent=2)+'\n')
    compiler = shutil.which('g++')
    require(compiler is not None, 'ordinary g++ compiler required')
    command = [compiler, *FLAGS, str(output/'software_recipe.cpp'), '-o', str(output/'software_recipe')]
    build = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output/'build.log').write_text(build.stdout+build.stderr)
    require(build.returncode == 0, 'ordinary C++ compile failed; see build.log')
    provenance.update(compile_command=command, compiler_version=subprocess.run([compiler,'--version'], capture_output=True, text=True, check=True).stdout.splitlines()[0],
                      generated_cpp_sha256=file_sha(output/'software_recipe.cpp'), generated_header_sha256=file_sha(output/'block_layout.h'),
                      binary_sha256=file_sha(output/'software_recipe'), generator_sha256=file_sha(Path(__file__)),
                      numerical_contract='qwen2-functional-bf16-fp32-ordered-v1', rounding_mode='FE_TONEAREST',
                      hardware_simulation=False, generated_by_chisel=False)
    (output/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return layout, provenance


def pack_readonly(layout: dict, tensors: dict[str, bytes], token_ids: list[int], output: Path) -> dict:
    require(not output.exists(), 'refuse arena overwrite')
    require(0 < len(token_ids) <= layout['max_tokens'], 'token count outside model capacity')
    require(all(type(t) is int and 0 <= t < 256 for t in token_ids), 'token outside acquired embedding rows')
    regions = {r['name']: r for r in layout['regions']}
    sizes = dict(layout, kv=layout['kv_heads']*layout['head_dim'])
    arena = np.zeros(layout['writable_start']//4, dtype='<f4')
    def decode(key: str, shape: tuple[int, ...]) -> np.ndarray:
        require(key in tensors, 'missing payload tensor '+key)
        raw = tensors[key]
        require(len(raw) == math.prod(shape)*2, 'BF16 payload size mismatch '+key)
        result = (np.frombuffer(raw,dtype='<u2').astype('<u4')<<16).view('<f4').reshape(shape)
        require(bool(np.isfinite(result).all()), 'nonfinite payload '+key)
        return result
    def put(name: str, values: np.ndarray) -> None:
        region = regions[name]
        flat = np.asarray(values,dtype='<f4').reshape(-1)
        require(region['external'] and flat.size <= region['words'], 'readonly region overflow '+name)
        arena[region['offset']//4:region['offset']//4+flat.size] = flat
    for region, (key, out_dim, in_dim) in WEIGHTS.items():
        put(region, decode(key, (sizes[out_dim],sizes[in_dim])).T)
    for region,key in VECTORS.items():
        put(region,decode(key,(regions[region]['words'],)))
    embeddings = decode('embed_tokens.rows_0_255',(256,layout['hidden']))
    put('x',embeddings[token_ids])
    # Match initialize() in the committed C++ recipe: double libm angles,
    # then convert each sin/cos value once into its FP32 arena container.
    angles=[[t/math.pow(1000000.0,2.0*i/layout['head_dim'])
             for i in range(layout['head_dim']//2)] for t in range(len(token_ids))]
    put('cos',np.array([[math.cos(a) for a in row] for row in angles],dtype='<f4'))
    put('sin',np.array([[math.sin(a) for a in row] for row in angles],dtype='<f4'))
    arena.tofile(output)
    x=embeddings[token_ids].astype('<f4').copy()
    x.tofile(output.parent/'input_x.f32le')
    return dict(readonly_bytes=output.stat().st_size, readonly_sha256=file_sha(output),
                input_x_sha256=sha(x.tobytes()), token_ids=token_ids, intermediate_preloads=0,
                rope_theta=1000000.0, positions=list(range(len(token_ids))),
                rope_table_recipe='canonical_cpp_initialize_double_libm_then_FP32')


def execute(generated: Path, arena: Path, tokens: int, output: Path, timeout_seconds: float = 600) -> float:
    require(0 < timeout_seconds <= 600, 'local run timeout must be in (0,600] seconds')
    start=time.monotonic()
    try:
        run=subprocess.run([str(generated/'software_recipe'),str(arena),str(tokens),str(output)],
                           capture_output=True,text=True,timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        (output/'run.log').write_text('TIMEOUT: ordinary C++ model exceeded bounded local budget\n')
        raise RuntimeError('software recipe timeout; no completion claimed') from error
    elapsed=time.monotonic()-start
    (output/'run.log').write_text(run.stdout+run.stderr)
    require(run.returncode == 0, 'software recipe failed; see run.log')
    require(run.stdout.count('SOFTWARE_FLOAT_ENV ')==1,'floating-point environment probes absent')
    require(run.stdout.count('SOFTWARE_RECIPE_STAGE ') == 15 and 'SOFTWARE_RECIPE_COMPLETE ' in run.stdout, 'incomplete software model')
    return elapsed


def run_recipe(root: Path, payload_dir: Path, output_dir: Path, tokens: int = 16,
               timeout_seconds: float = 600, m16_prerequisite: Path | None = None,
               diagnostic_m128: bool = False) -> dict:
    root, output_dir = root.resolve(), output_dir.resolve()
    require(tokens in (16,128), 'production software gate supports M16 and M128')
    require(tokens!=128 or m16_prerequisite is not None,'M128 requires a completed M16 prerequisite')
    require(not diagnostic_m128 or tokens==128,'diagnostic M128 mode requires 128 tokens')
    require(not output_dir.exists(), 'refuse existing model run directory')
    spec=importlib.util.spec_from_file_location('recipe_payload',root/'scripts/qwen2_layer0_payload.py')
    require(spec is not None and spec.loader is not None, 'payload loader unavailable')
    sys.path.insert(0,str(root/'src'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest, tensors=module.load_payload(root,payload_dir)
    output_dir.mkdir(parents=True)
    layout,provenance=generate_and_compile(root,output_dir/'generated')
    packed=pack_readonly(layout,tensors,list(range(tokens)),output_dir/'readonly_arena.f32le')
    prerequisite=verify_m16_prerequisite(root,m16_prerequisite,manifest,provenance,output_dir/'input_x.f32le',allow_accuracy_failure=diagnostic_m128) if tokens==128 else None
    # Discard the 94 MB transport bytes before executing the single arena model.
    del tensors
    elapsed=execute(output_dir/'generated',output_dir/'readonly_arena.f32le',tokens,output_dir,timeout_seconds)
    require(file_sha(output_dir/'readonly_arena.f32le')==packed['readonly_sha256'],'readonly arena changed during execution')
    environment_line=next(line for line in (output_dir/'run.log').read_text().splitlines() if line.startswith('SOFTWARE_FLOAT_ENV '))
    float_environment=dict(re.findall(r'(\w+)=([^ ]+)',environment_line))
    stages=[]
    for phase,name in enumerate(STAGE_NAMES):
        path=output_dir/f'phase_{phase}_{name}_recipe.f32le'
        width=next(r['words']//layout['max_tokens'] for r in layout['regions'] if r['name']==name)
        require(path.stat().st_size==tokens*width*4,'stage output size mismatch '+name)
        stages.append(dict(phase=phase,name=name,shape=[tokens,width],path=path.name,sha256=file_sha(path)))
    result=dict(schema=1,status='DIAGNOSTIC_NOT_ACCEPTED' if diagnostic_m128 else 'COMPLETE_SOFTWARE_HARDWARE_RECIPE',
                diagnostic_only=diagnostic_m128,completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE',shape=dict(SHAPE,tokens=tokens),
                checkpoint_manifest=manifest,checkpoint_manifest_sha256=file_sha(payload_dir/'manifest.json'),
                checkpoint_payload_directory=str(payload_dir.resolve()),input=packed,stages=stages,source_identity=provenance,
                logical_macs=logical_macs(tokens),wall_seconds=elapsed,hardware_cycles=None,hardware_utilization=None,
                float_environment=float_environment,m16_prerequisite=prerequisite,
                estimated_m128_wall_seconds=elapsed*logical_macs(128)['total']/logical_macs(tokens)['total'],
                scope=dict(software_only=True,all_15_stages=True,consumes_own_previous_stages=True,
                           rtl_executed=False,physical_resource_validation=False,official_framework_forward=False,
                           checkpoint_accuracy_signoff=False,multi_layer=False,kv_cache_carry=False))
    (output_dir/'RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result




def verify_m16_prerequisite(root: Path, directory: Path, manifest: dict,
                            provenance: dict, input_path: Path, allow_accuracy_failure: bool = False) -> dict:
    """Refuse larger execution without intact, same-recipe M16 evidence."""
    result_path=directory/'RESULT.json';comparison_path=directory/'REFERENCE_COMPARISON.json'
    result=json.loads(result_path.read_text());comparison=json.loads(comparison_path.read_text())
    validate_recipe_receipt(root,directory)
    require(result['status']=='COMPLETE_SOFTWARE_HARDWARE_RECIPE' and result['shape']==dict(SHAPE,tokens=16),'incomplete M16 recipe prerequisite')
    require(result['checkpoint_manifest']==manifest,'M16 prerequisite payload differs')
    for key in ('source_sha256','committed_cpp_sha256','section_sha256','generated_cpp_sha256',
                'generated_header_sha256','compiler_version','generator_sha256','numerical_contract','rounding_mode'):
        require(result['source_identity'][key]==provenance[key],'M16 prerequisite source/compiler recipe differs: '+key)
    require(result['source_identity']['compile_command'][1:5]==FLAGS,'M16 prerequisite compiler flags differ')
    require(result['float_environment']['rounding']=='FE_TONEAREST' and result['float_environment']['probes']=='10','M16 float environment unverified')
    require(result['input']['token_ids']==list(range(16)),'M16 prerequisite token sequence differs')
    prefix=(directory/'input_x.f32le').read_bytes()
    require(len(prefix)==16*SHAPE['hidden']*4 and sha(prefix)==result['input']['input_x_sha256']
            and input_path.read_bytes()[:len(prefix)]==prefix,'M16 prerequisite input prefix differs')
    require([item['name'] for item in result['stages']]==list(STAGE_NAMES),'M16 prerequisite missing/reordered stage')
    for item in result['stages']:
        path=directory/item['path'];raw=path.read_bytes()
        require(sha(raw)==item['sha256'] and len(raw)==math.prod(item['shape'])*4
                and bool(np.isfinite(np.frombuffer(raw,dtype='<f4')).all()),'M16 prerequisite stage changed or invalid')
    accuracy_passed=(comparison['native_gate_status']=='PASS_BF16_STAGE_BUDGET'
                     and comparison['status']=='PASS_EXISTING_FP32_FINAL_BUDGET')
    require(allow_accuracy_failure or accuracy_passed,'M128 blocked by failed M16 numerical gate; explicit diagnostic mode required')
    require(comparison['tokens']==16 and comparison['recipe_result_sha256']==file_sha(result_path),'M16 final comparison absent or stale')
    require(comparison['budget']==existing_budget(root),'M16 comparison budget changed')
    recomputed=build_comparison(root,directory,Path(comparison['native_directory']))
    require(recomputed==comparison,'M16 comparison diagnostics/verdict/artifacts changed')
    require(result['estimated_m128_wall_seconds']<=600,'M128 estimated runtime exceeds local ten-minute budget')
    return dict(directory=str(directory),result_sha256=file_sha(result_path),comparison_sha256=file_sha(comparison_path),
                estimated_m128_wall_seconds=result['estimated_m128_wall_seconds'],
                numerical_gate_passed=accuracy_passed,diagnostic_only=allow_accuracy_failure,
                inherited_comparison_status=comparison['status'],inherited_native_status=comparison['native_gate_status'])

def existing_budget(root: Path) -> dict:
    """Read, never invent or relax, the existing final hidden-output budget."""
    source=root/'chisel/continuous_prefill/scripts/compare_qwen2_stack_reference.py'
    committed=subprocess.run(['git','show','HEAD:'+str(source.relative_to(root))],cwd=root,
                             check=True,capture_output=True,text=True,timeout=15).stdout
    names={'MAX_RELATIVE_L2':'max_relative_l2','MIN_COSINE':'min_cosine','MAX_NORMALIZED_ABS':'max_normalized_abs'}
    values={}
    lines=committed.splitlines(keepends=True)
    fragment=[]
    for node in ast.parse(committed).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name in names:
                require(name not in values and isinstance(node.value,ast.Constant)
                        and type(node.value.value) in (float,int), 'unrecognized existing budget')
                values[name]=float(node.value.value)
                fragment.extend(lines[node.lineno-1:node.end_lineno])
    require(set(values)==set(names),'existing final-output budget missing')
    fragment=''.join(fragment)
    require(sha(fragment.encode())=='7d15a86b3affed31d77814b18fd9d0884fa3c0634733a9bae26aac43d99fb6bf',
            'existing budget constant fragment changed; explicit review required')
    return dict(thresholds={names[key]:value for key,value in values.items()},
                source=str(source.relative_to(root)),source_fragment_sha256=sha(fragment.encode()),
                source_fragment=fragment,source_kind='pinned_committed_constants_only_not_executed',
                scope='developer_defined_final_output_bringup_budget_not_model_quality_guarantee')


def error_metrics(actual: np.ndarray, reference: np.ndarray) -> dict:
    a=np.asarray(actual,dtype=np.float64).reshape(-1)
    r=np.asarray(reference,dtype=np.float64).reshape(-1)
    require(a.shape==r.shape and a.size>0,'reference tensor shape mismatch')
    require(bool(np.isfinite(a).all() and np.isfinite(r).all()),'nonfinite comparison tensor')
    delta=a-r; an=float(np.linalg.norm(a)); rn=float(np.linalg.norm(r)); en=float(np.linalg.norm(delta))
    cosine=1.0 if an==rn==0 else 0.0 if an==0 or rn==0 else float(np.dot(a,r)/(an*rn))
    maximum=float(np.max(np.abs(delta))); scale=float(np.max(np.abs(r)))
    return dict(relative_l2=en/rn if rn else (0.0 if en==0 else None),cosine=cosine,
                max_abs=maximum,mean_abs=float(np.mean(np.abs(delta))),
                normalized_max_abs=maximum/scale if scale else (0.0 if maximum==0 else None))



def load_module(path: Path, name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,'module unavailable: '+str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_recipe_receipt(root: Path, directory: Path) -> dict:
    receipt=json.loads((directory/'RESULT.json').read_text())
    tokens=receipt['shape']['tokens']
    require(tokens in (16,128) and receipt['shape']==dict(SHAPE,tokens=tokens)
            and receipt['status'] in ('COMPLETE_SOFTWARE_HARDWARE_RECIPE','DIAGNOSTIC_NOT_ACCEPTED'),'invalid completed recipe geometry/status')
    require(receipt['status']!='DIAGNOSTIC_NOT_ACCEPTED' or (tokens==128 and receipt['diagnostic_only'] is True),'invalid diagnostic-only scope')
    require([entry['name'] for entry in receipt['stages']]==list(STAGE_NAMES),'recipe stage inventory/order mismatch')
    layout=make_layout();regions={r['name']:r for r in layout['regions']}
    for phase,entry in enumerate(receipt['stages']):
        name=STAGE_NAMES[phase];relative=f'phase_{phase}_{name}_recipe.f32le'
        width=regions[name]['words']//SHAPE['max_tokens']
        require(entry['phase']==phase and entry['shape']==[tokens,width] and entry['path']==relative,'recipe stage shape/path mismatch')
        path=directory/relative
        require(not path.is_symlink() and path.stat().st_size==tokens*width*4 and file_sha(path)==entry['sha256'],'recipe stage bytes/hash mismatch')
        require(bool(np.isfinite(np.fromfile(path,dtype='<f4')).all()),'recipe stage nonfinite')
    readonly=directory/'readonly_arena.f32le'
    require(not readonly.is_symlink() and readonly.stat().st_size==receipt['input']['readonly_bytes']==layout['writable_start']
            and file_sha(readonly)==receipt['input']['readonly_sha256'],'recipe readonly arena bytes/hash mismatch')
    expected_input=directory/'input_x.f32le'
    require(expected_input.stat().st_size==tokens*SHAPE['hidden']*4 and file_sha(expected_input)==receipt['input']['input_x_sha256']
            and receipt['input']['token_ids']==list(range(tokens)),'recipe input identity mismatch')
    _,_,current=extract_sources(root)
    for key in ('source_sha256','committed_cpp_sha256','section_sha256'):
        require(receipt['source_identity'][key]==current[key],'recipe source identity changed: '+key)
    require(receipt['source_identity']['generator_sha256']==file_sha(Path(__file__)),'recipe generator source changed')
    require(receipt['source_identity']['compile_command'][1:5]==FLAGS,'recipe compile flags differ')
    for name,key in [('software_recipe.cpp','generated_cpp_sha256'),('block_layout.h','generated_header_sha256'),('software_recipe','binary_sha256')]:
        require(file_sha(directory/'generated'/name)==receipt['source_identity'][key],'recipe generated artifact changed')
    payload_dir=Path(receipt['checkpoint_payload_directory'])
    require(file_sha(payload_dir/'manifest.json')==receipt['checkpoint_manifest_sha256'],'recipe checkpoint manifest changed')
    sys.path.insert(0,str(root/'src'))
    payload_module=load_module(root/'scripts/qwen2_layer0_payload.py','comparison_payload')
    manifest,tensors=payload_module.load_payload(root,payload_dir)
    require(manifest==receipt['checkpoint_manifest'],'recipe checkpoint identity differs')
    embeddings=(np.frombuffer(tensors['embed_tokens.rows_0_255'],dtype='<u2').astype('<u4')<<16).view('<f4').reshape(256,SHAPE['hidden'])
    require(embeddings[:tokens].tobytes()==expected_input.read_bytes(),'recipe input differs from pinned embedding rows')
    return receipt


def validate_native_receipt(root: Path, directory: Path, recipe: dict) -> dict:
    report=json.loads((directory/'RESULT.json').read_text())
    tokens=recipe['shape']['tokens']
    module=load_module(root/'scripts/qwen2_layer0_model_gate.py','recipe_native_validator')
    require(report['schema_version']==1 and report['tokens']==tokens and report['layer']==0
            and report['model_id']=='Qwen/Qwen2-1.5B-Instruct' and report['status'] in ('PASS_BF16_STAGE_BUDGET','FAIL_BF16_STAGE_BUDGET')
            and report['official_framework_forward'] is True and report['rtl_execution'] is False,'native gate status/scope mismatch')
    identity=report['identity']
    require(identity['source_sha256']==module.SOURCE_HASHES and identity['model_revision']==module.MODEL_REVISION
            and identity['forward_revision']==module.FORWARD_REVISION and identity['installed_sources_verified_exact'] is True
            and identity['runner_sha256']==file_sha(root/'scripts/qwen2_layer0_model_gate.py'),'native source/runner identity mismatch')
    for name,digest in module.SOURCE_HASHES.items():
        require(file_sha(root/module.SOURCE/name)==digest,'pinned official source changed')
    require(report['payload_manifest_sha256']==recipe['checkpoint_manifest_sha256'],'native/recipe payload mismatch')
    policy=module.load_policy(root)
    require(report['policy']==policy and set(report['modes'])=={'bf16','fp32'},'native policy/mode inventory changed')
    config=json.loads((root/module.SOURCE/'config.json').read_text())
    any_failure=False
    for mode in ('bf16','fp32'):
        phases=report['modes'][mode]['phases']
        require(len(phases)==(2 if report['carried'] else 1),'native phase inventory mismatch')
        previous={'native':None,'independent':None}
        for phase,record in enumerate(phases):
            ids=list(range(phase*tokens,(phase+1)*tokens))
            require(record['phase']==phase and record['past_tokens']==phase*tokens and record['token_ids']==record['position_ids']==ids
                    and record['all_semantics_exact'] is True
                    and all(v is True for v in record['semantics'].values()),'native phase/input/semantic gate mismatch')
            expected_status=('FAIL_BF16_STAGE_BUDGET' if record['failed_stages'] else 'PASS_BF16_STAGE_BUDGET') if mode=='bf16' else 'DIAGNOSTIC_FP32'
            require(record['status']==expected_status,'native phase status mismatch')
            any_failure |= bool(record['failed_stages'])
            recomputed_failed=[]
            shapes=module.expected_shapes(config,tokens,phase*tokens)
            require(set(record['stages'])==module.REQUIRED_STAGES,'native stage inventory mismatch')
            loaded={'native':{},'independent':{}}
            for name,entry in record['stages'].items():
                require(entry['shape']==shapes[name],'native stage shape mismatch')
                for kind in ('native','independent'):
                    relative=f'{mode}/phase_{phase}/{kind}_{name}.f32le';path=directory/relative
                    require(entry[kind+'_file']==relative and not path.is_symlink()
                            and path.stat().st_size==math.prod(shapes[name])*4
                            and file_sha(path)==entry[kind+'_file_sha256'],'native tensor path/bytes/hash mismatch')
                    array=np.fromfile(path,dtype='<f4')
                    if name in module.EXPORT_TOKEN_MAJOR:
                        b,h,t,d=shapes[name];export_shape=[b,t,h*d]
                        array=array.reshape(b,t,h,d).transpose(0,2,1,3).copy()
                    else:
                        export_shape=shapes[name];array=array.reshape(shapes[name])
                    require(entry[kind+'_export_shape']==export_shape,'native tensor export shape mismatch')
                    loaded[kind][name]=array
                metrics=module.compare(loaded['native'][name],loaded['independent'][name])
                require(all(entry.get(k)==v for k,v in metrics.items()),'native stored diagnostic mismatch: '+name)
                native_array=loaded['native'][name]
                is_bf16=mode=='bf16' and name!='softmax_fp32'
                require(not is_bf16 or not bool(np.any(native_array.view('<u4') & 0xffff)),'native BF16 export not representable')
                stored=(native_array.view('<u4')>>16).astype('<u2') if is_bf16 else native_array
                require(entry['actual_storage_dtype']==('torch.bfloat16' if is_bf16 else 'torch.float32')
                        and module.digest_array(stored)==entry['actual_storage_sha256'],'native original storage identity mismatch')
                verdict=module.stage_verdict(name,metrics,mode,policy)
                require(all(entry.get(k)==v for k,v in verdict.items()),'native stored stage verdict mismatch')
                if verdict['passed'] is False:recomputed_failed.append(name)
            require(sorted(record['failed_stages'])==sorted(recomputed_failed),'native failed-stage inventory mismatch')
            for kind in ('native','independent'):
                if phase==0:
                    require(sha(loaded[kind]['x'].tobytes())==recipe['input']['input_x_sha256'],'native/recipe input bytes differ')
                require(all(module.audit_semantics(loaded[kind],previous[kind],config,mode).values()),'native recomputed semantic failure')
                previous[kind]=loaded[kind]
    require(report['status']==('FAIL_BF16_STAGE_BUDGET' if any_failure else 'PASS_BF16_STAGE_BUDGET'),'native overall status differs from recomputed stage gates')
    return report


def compare_references(root: Path, recipe_dir: Path, native_dir: Path) -> dict:
    target=recipe_dir/'REFERENCE_COMPARISON.json'
    require(not target.exists(),'refuse comparison overwrite')
    result=build_comparison(root,recipe_dir,native_dir)
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def build_comparison(root: Path, recipe_dir: Path, native_dir: Path) -> dict:
    """Recompute from both bound receipts and every artifact; never trust PASS."""
    receipt=validate_recipe_receipt(root,recipe_dir)
    native=validate_native_receipt(root,native_dir,receipt)
    tokens=receipt['shape']['tokens']
    budget=existing_budget(root)
    comparisons=[]
    for dtype in ('bf16','fp32'):
        for reference_kind in ('native','independent'):
            stages=[]
            for item in receipt['stages']:
                actual_path=recipe_dir/item['path']
                reference_path=native_dir/dtype/'phase_0'/f'{reference_kind}_{item["name"]}.f32le'
                reference=np.fromfile(reference_path,dtype='<f4')
                actual=np.fromfile(actual_path,dtype='<f4')
                metrics=error_metrics(actual,reference)
                stages.append(dict(name=item['name'],phase=item['phase'],metrics=metrics,
                                   bit_differences=int(np.count_nonzero(actual.view('<u4')!=reference.view('<u4'))),
                                   reference_sha256=file_sha(reference_path)))
            final=next(stage for stage in stages if stage['name']=='y')['metrics'];thresholds=budget['thresholds']
            passed=(final['relative_l2'] is not None and final['normalized_max_abs'] is not None
                    and final['relative_l2']<=thresholds['max_relative_l2']
                    and final['cosine']>=thresholds['min_cosine']
                    and final['normalized_max_abs']<=thresholds['max_normalized_abs']) if dtype=='fp32' else None
            comparisons.append(dict(reference_dtype=dtype,reference_kind=reference_kind,stages=stages,
                                    first_differing_stage=next((s['name'] for s in stages if s['bit_differences']),None),
                                    final_fp32_bringup_budget_pass=passed))
    budget_pass=all(x['final_fp32_bringup_budget_pass'] for x in comparisons if x['reference_dtype']=='fp32')
    budget_status='PASS_EXISTING_FP32_FINAL_BUDGET' if budget_pass else 'FAIL_EXISTING_FP32_FINAL_BUDGET'
    return dict(schema=1,tokens=tokens,phase='cold_prefill',budget=budget,comparisons=comparisons,
                recipe_result_sha256=file_sha(recipe_dir/'RESULT.json'),native_result_sha256=file_sha(native_dir/'RESULT.json'),
                native_directory=str(native_dir.resolve()),native_gate_status=native['status'],
                comparator_sha256=file_sha(Path(__file__)),
                diagnostic_interpretation='Stage differences are preserved: recipe BF16 ingress, ordered FP32 FMA/reductions and polynomial exponential differ from native framework arithmetic. Only the preexisting final FP32 budget is evaluated.',
                status='DIAGNOSTIC_NOT_ACCEPTED' if receipt.get('diagnostic_only') else
                    budget_status if native['status']=='PASS_BF16_STAGE_BUDGET' else 'FAIL_NATIVE_STAGE_BUDGET',
                diagnostic_only=bool(receipt.get('diagnostic_only')),
                final_fp32_budget_status=budget_status,
                per_stage_thresholds=None,bf16_acceptance_thresholds=None,
                hardware_cycles=None,hardware_utilization=None,rtl_executed=False)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tokens',type=int,choices=(16,128),default=16)
    parser.add_argument('--timeout-seconds',type=float,default=600)
    parser.add_argument('--m16-prerequisite',type=Path)
    parser.add_argument('--diagnostic-m128',action='store_true',help='Permit accuracy-failed but intact M16 evidence; output remains NOT_ACCEPTED and exit status is nonzero')
    args=parser.parse_args()
    result=run_recipe(args.root,args.payload,args.out,args.tokens,args.timeout_seconds,args.m16_prerequisite,args.diagnostic_m128)
    print(json.dumps({key:result[key] for key in ('status','logical_macs','wall_seconds','estimated_m128_wall_seconds','hardware_cycles','hardware_utilization')},indent=2))
    return 1 if result['diagnostic_only'] else 0


if __name__=='__main__':
    raise SystemExit(main())
