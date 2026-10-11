#!/usr/bin/env python3
"""Bounded, software-only resident Dense/optional Attention v0 storage model.

Dense is always mapped; --rectangular-attention also maps attention() using the
published five-context rectangular candidate. No arithmetic policy, native
reference, payload loader, or RTL is implemented here. All results remain
DIAGNOSTIC_NOT_ACCEPTED. The
readonly arena is the existing expanded FP32 *fixture*, not a BF16 DDR image;
reported BF16 weight traffic is logical transport accounting, not executed iDMA.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA256 = '2b7a4384bc619d39546714b251f286708646029eea172de8c28fb4946b69a2f6'
SCHEDULE_SHA256 = '47e8f3acd6b7dafe4e6fe731cae20205ab93c6208af12b48eb01373edcaa2175'
ATTENTION_EVENT_SHA256 = 'fbf1c610be695256f487e1df971c266575dc8d722195cd919f06f1209034fbe8'
SOURCE_PASS_COMMIT = '299949a03876fb561010afb6e1d83097db0ca593'
STATUS = 'DIAGNOSTIC_NOT_ACCEPTED'
MAPPING = 'resident_m128_nc3'
spec = importlib.util.spec_from_file_location('resident_base_recipe', ROOT/'scripts/qwen2_block_recipe_model.py')
assert spec is not None and spec.loader is not None
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def _module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ATT = _module('qwen2_rectangular_attention_model')
NUMERIC_ATT = _module('qwen2_rectangular_attention_numeric')

# This is intentionally inside dense(): the other guarded methods, driver,
# floating-point probes, and includes are reused without substitutions.
DENSE_BODY = r'''
    need(tokens>0 && tokens<=128 && K>0 && N>0 && K%16==0 && N%16==0,
         "resident Dense shape outside bounded storage");
    const bool fullA=K<=1536;
    const int kc=256, nc=256, slots=fullA?1:3, aDepth=fullA?K:kc;
    const int aWords=128*aDepth*2/(16*32), cBase=aWords;
    need(cBase+slots*256<=1024,"resident A/C partition overflow");
    struct Physical {
      // Actual 32-byte SRAM words: BF16 halfwords; FP32 C shares A's bytes.
      uint16_t ac[16][1024][16], b[16][512][16];
      float accumulator[5][16][256], resultFIFO[2][16][256], finalValue[16][256];
      // Tags are observer metadata only, never copies of numerical payloads.
      int prefix[3][8], ownerN[3][8];
      unsigned fifoHead=0, fifoCount=0, fifoHigh=0, contextHigh=0;
      bool finalLive=false;
      uint64_t aReads=0, wReads=0, dWrites=0, seeds=0, stores=0;
      uint64_t restores=0, snapshots=0, issues=0, macs=0, captures=0;
      Physical(){
        for(auto& bank:ac)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
        for(auto& bank:b)for(auto& word:bank)for(auto& x:word)x=0x7fc1;
        for(auto& ctx:accumulator)for(auto& row:ctx)for(auto& x:row)x=fp(0x7fc00001u);
        for(auto& entry:resultFIFO)for(auto& row:entry)for(auto& x:row)x=fp(0x7fc00001u);
        for(auto& row:finalValue)for(auto& x:row)x=fp(0x7fc00001u);
        for(int s=0;s<3;s++)for(int mt=0;mt<8;mt++){prefix[s][mt]=-1;ownerN[s][mt]=-1;}
      }
      uint16_t& aCell(int row,int depth,int stride){
        const int bank=row%16, word=(row/16)*(stride/16)+depth/16, lane=depth%16;
        if(!(row>=0 && row<128 && depth>=0 && depth<stride && word<1024))
          need(false,"resident A address out of bounds");
        // bank/word/lane is a physical byte address, not a private tile slot.
        const size_t address=(size_t(bank)*1024+word)*32+lane*2;
        if(address>=sizeof(ac))need(false,"resident A physical byte address overflow");
        return ac[bank][word][lane];
      }
      uint16_t& bCell(int depth,int col){
        // Both 256-word halves exist. Serial schedule uses half zero only.
        const int bank=col/16, word=depth, lane=col%16;
        if(!(depth>=0 && depth<256 && col>=0 && col<256))
          need(false,"resident B address out of bounds");
        const size_t address=(size_t(bank)*512+word)*32+lane*2;
        if(address>=sizeof(b))need(false,"resident B physical byte address overflow");
        return b[bank][word][lane];
      }
      float operand(uint16_t value){
        if((value&0x7f80)==0x7f80)need(false,"resident uninitialized or nonfinite operand");
        return fp(uint32_t(value)<<16);
      }
      uint16_t* cCell(int base,int slot,int row,int col){
        const int bank=row%16, word=base+slot*256+(row/16)*32+col/8, lane=2*(col%8);
        if(!(base>=0 && slot>=0 && slot<3 && row>=0 && row<128 && col>=0 && col<256 &&
             word>=base && word<1024 && lane+1<16))need(false,"resident C address out of bounds");
        const size_t address=(size_t(bank)*1024+word)*32+lane*2;
        if(address%4 || address+4>sizeof(ac))need(false,"resident C physical address/alignment");
        return &ac[bank][word][lane];
      }
      void save(int base,int slot,int row,int col,float value){
        auto* cell=cCell(base,slot,row,col);uint32_t u=bits(value);
        if(!std::isfinite(value))need(false,"resident nonfinite prefix store");
        cell[0]=uint16_t(u);cell[1]=uint16_t(u>>16);stores++;
      }
      float restore(int base,int slot,int row,int col){
        auto* cell=cCell(base,slot,row,col);float value=fp(uint32_t(cell[0])|(uint32_t(cell[1])<<16));
        if(!std::isfinite(value))need(false,"resident uninitialized FP32 prefix");
        seeds++;return value;
      }
    };
    static_assert(sizeof(Physical::ac)==524288 && sizeof(Physical::b)==262144,
                  "resident scratch must be exactly 768 KiB");
    static_assert(sizeof(Physical::accumulator)==5*16*256*4 &&
                  sizeof(Physical::resultFIFO)==2*16*256*4 && sizeof(Physical::finalValue)==16*256*4,
                  "resident register capacities changed");
    auto storage=std::make_unique<Physical>();auto& p=*storage;
    auto loadA=[&](int kb,int depths){
      for(unsigned row=0;row<tokens;row++)for(int kk=0;kk<depths;kk++){
        float value=bf(get(in,size_t(row)*K+kb+kk));
        need(std::isfinite(value),"resident nonfinite A materialization");
        p.aCell(row,fullA?kb+kk:kk,aDepth)=uint16_t(bits(value)>>16);p.aReads++;
      }
    };
    if(fullA)loadA(0,K);
    for(int ng=0;ng<N;ng+=slots*nc){
      const int liveSlots=std::min(slots,(N-ng+nc-1)/nc);
      for(int slot=0;slot<liveSlots;slot++)for(int mt=0;mt<8;mt++){
        p.prefix[slot][mt]=-1;p.ownerN[slot][mt]=-1;
        for(int row=mt*16;row<(mt+1)*16;row++)for(int col=0;col<nc;col++){
          auto* cell=p.cCell(cBase,slot,row,col);cell[0]=1;cell[1]=0x7fc0;
        }
      }
      for(int kb=0;kb<K;kb+=kc){
        const int depths=std::min(kc,K-kb);const bool final=kb+depths==K;
        if(!fullA)loadA(kb,depths);
        for(int slot=0;slot<liveSlots;slot++){
          const int nb=ng+slot*nc, columns=std::min(nc,N-nb);
          for(int kk=0;kk<depths;kk++)for(int col=0;col<columns;col++){
            float value=get(w,size_t(kb+kk)*N+nb+col);
            // The arena expands BF16 for fixture compatibility. Do not silently
            // count arbitrary FP32 fixture weights as BF16 transport.
            need(std::isfinite(value) && bits(value)==bits(bf(value)),"resident weight not exact BF16");
            p.bCell(kk,col)=uint16_t(bits(value)>>16);p.wReads++;
          }
          for(unsigned mb=0;mb<tokens;mb+=80){
            const int count=std::min(5,int((tokens-mb+15)/16));
            p.contextHigh=std::max(p.contextHigh,unsigned(count));
            need(p.fifoCount==0 && !p.finalLive,"resident context reuse before drain");
            for(int ctx=0;ctx<count;ctx++){
              const int first=mb+ctx*16, rows=std::min(16,int(tokens)-first), mt=first/16;
              if(kb)need(p.prefix[slot][mt]==kb && p.ownerN[slot][mt]==nb,
                         "resident stale or aliased prefix identity");
              else need(p.prefix[slot][mt]==-1,"resident duplicate first prefix");
              for(int row=0;row<rows;row++)for(int col=0;col<columns;col++)
                p.accumulator[ctx][row][col]=kb?p.restore(cBase,slot,first+row,col):0.0f;
              if(kb)p.restores++;
            }
            auto issue=[&](int ctx,int kk){
              const int first=mb+ctx*16, rows=std::min(16,int(tokens)-first);
              for(int row=0;row<rows;row++){
                float av=p.operand(p.aCell(first+row,fullA?kb+kk:kk,aDepth));
                for(int col=0;col<columns;col++)
                  p.accumulator[ctx][row][col]=std::fma(av,p.operand(p.bCell(kk,col)),p.accumulator[ctx][row][col]);
              }
              p.issues++;p.macs+=uint64_t(rows)*columns;
            };
            // Increasing K within every lane, including across SRAM snapshots.
            for(int kk=0;kk<depths-1;kk++)for(int ctx=0;ctx<count;ctx++)issue(ctx,kk);
            for(int ctx=0;ctx<count;ctx++){
              issue(ctx,depths-1);
              const int first=mb+ctx*16, rows=std::min(16,int(tokens)-first), mt=first/16;
              need(p.fifoCount<2 && !p.finalLive,"resident result storage overflow");
              const int tail=(p.fifoHead+p.fifoCount)%2;
              for(int row=0;row<rows;row++)for(int col=0;col<columns;col++){
                p.resultFIFO[tail][row][col]=p.accumulator[ctx][row][col];
                p.accumulator[ctx][row][col]=fp(0x7fc00001u);
              }
              p.fifoCount++;p.fifoHigh=std::max(p.fifoHigh,p.fifoCount);p.finalLive=true;
              for(int row=0;row<rows;row++)for(int col=0;col<columns;col++){
                p.finalValue[row][col]=p.resultFIFO[p.fifoHead][row][col];
                p.resultFIFO[p.fifoHead][row][col]=fp(0x7fc00001u);
              }
              p.fifoHead=(p.fifoHead+1)%2;p.fifoCount--;p.captures++;
              for(int row=0;row<rows;row++)for(int col=0;col<columns;col++){
                const float value=p.finalValue[row][col];
                if(final){
                  const size_t ix=size_t(first+row)*N+nb+col;
                  need(bits(get(out,ix))==0x7fc00001u,"resident output overwritten before final K");
                  put(out,ix,bias>=0?add(value,get(bias,nb+col)):value);p.dWrites++;
                }else p.save(cBase,slot,first+row,col,value);
                p.finalValue[row][col]=fp(0x7fc00001u);
              }
              p.prefix[slot][mt]=kb+depths;p.ownerN[slot][mt]=nb;
              if(!final)p.snapshots++;
              p.finalLive=false;
            }
          }
        }
      }
    }
    const uint64_t kt=(K+255)/256, nt=(N+255)/256, mt=(tokens+15)/16, ng=(nt+slots-1)/slots;
    need(p.aReads==uint64_t(tokens)*K*(fullA?1:ng) && p.wReads==uint64_t(K)*N &&
         p.dWrites==uint64_t(tokens)*N,"resident external operand/output counts");
    need(p.seeds==uint64_t(tokens)*N*(kt-1) && p.stores==p.seeds &&
         p.restores==mt*nt*(kt-1) && p.snapshots==p.restores,"resident FP32 seed/store counts");
    need(p.macs==uint64_t(tokens)*K*N && p.issues==mt*nt*K && p.captures==mt*nt*kt,
         "resident increasing K issue counts");
    need(p.contextHigh<=5 && p.fifoHigh==1 && p.fifoCount==0 && !p.finalLive,
         "resident final drain/capacity");
    std::cout<<"RESIDENT_DENSE tokens="<<tokens<<" k="<<K<<" n="<<N
      <<" full_a="<<fullA<<" c_slots="<<slots<<" c_base_word="<<cBase
      <<" scratch_bytes="<<(sizeof(p.ac)+sizeof(p.b))<<" contexts_peak="<<p.contextHigh
      <<" fifo_peak="<<p.fifoHigh<<" final_peak=1"
      <<" external_a_fp32_bytes="<<p.aReads*4<<" logical_weight_bf16_bytes="<<p.wReads*2
      <<" external_d_fp32_bytes="<<p.dWrites*4<<" prefix_restore_fp32_bytes="<<p.seeds*4
      <<" prefix_store_fp32_bytes="<<p.stores*4<<" seed_contexts="<<p.restores
      <<" snapshot_contexts="<<p.snapshots<<" wide_issues="<<p.issues<<" useful_macs="<<p.macs
      <<" captures="<<p.captures<<" status=DIAGNOSTIC_NOT_ACCEPTED"<<std::endl;
'''


def frozen_sources(root: Path) -> tuple[str, str, dict]:
    """Bind every new source-pass comparison to immutable original v0 source."""
    helpers, maths, identity = R.extract_sources(root)
    committed = subprocess.run(['git', 'show', SOURCE_PASS_COMMIT+':'+R.SOURCE],
        cwd=root, check=True, capture_output=True, text=True, timeout=15).stdout
    R.require(R.section(committed, '#include "block_layout.h"', 'struct Pending') == helpers
              and R.section(committed, '  void norm(', '  void compareStage(') == maths,
              'canonical arithmetic differs from immutable source-pass reference')
    identity.update(source_pass_reference_commit=SOURCE_PASS_COMMIT,
                    source_pass_cpp_sha256=R.sha(committed.encode()))
    return helpers, maths, identity


def resident_source(root: Path, *, rectangular_attention: bool = False) -> tuple[str, dict]:
    R.require(R.file_sha(root/'scripts/qwen2_block_recipe_model.py') == BASE_SHA256,
              'base runner changed; explicit review required')
    R.require(R.file_sha(root/'scripts/qwen2_prefill_resource_schedule.py') == SCHEDULE_SHA256,
              'resident schedule changed; explicit review required')
    R.require(type(rectangular_attention) is bool, 'rectangular Attention opt-in must be boolean')
    helpers, maths, identity = frozen_sources(root)
    original = R.section(maths, '  void dense(', '  void rope(')
    signature = original[:original.index('{')+1]
    replacement = signature + DENSE_BODY + '  }\n'
    patched = maths.replace(original, replacement)
    restored = patched.replace(replacement, original)
    support = ''
    if rectangular_attention:
        R.require(R.file_sha(root/'scripts/qwen2_rectangular_attention_model.py') == ATTENTION_EVENT_SHA256,
                  'rectangular Attention event model changed; explicit review required')
        attention = R.section(maths, '  void attention(', '  void computeReference(')
        mapped = attention[:attention.index('{')+1] + NUMERIC_ATT.ATTENTION_BODY + '  }\n'
        patched = patched.replace(attention, mapped)
        restored = patched.replace(replacement, original).replace(mapped, attention)
        support = NUMERIC_ATT.CPP_SUPPORT
        identity.update(attention_event_sha256=ATTENTION_EVENT_SHA256,
                        attention_helper_sha256=R.file_sha(root/'scripts/qwen2_rectangular_attention_numeric.py'),
                        replaced_attention_sha256=R.sha(attention.encode()),
                        resident_attention_body_sha256=R.sha(NUMERIC_ATT.ATTENTION_BODY.encode()),
                        non_replaced_math_sha256=R.sha(maths.replace(original,'').replace(attention,'').encode()))
    R.require(restored == maths, 'unmapped canonical arithmetic changed')
    text = '// Ordinary C++ software numerical model; not a hardware simulator.\n'
    text += helpers + R.HOST_PROBES + support + R.DRIVER + patched + R.MAIN
    R.require(not re.search(r'Verilat|verilat|BlockDut|VQwen|d\.eval|DUT', text),
              'hardware symbol in software model')
    identity.update(base_runner_sha256=BASE_SHA256, schedule_sha256=SCHEDULE_SHA256,
                    replaced_dense_sha256=R.sha(original.encode()),
                    non_dense_math_sha256=R.sha(maths.replace(original, '').encode()),
                    resident_dense_body_sha256=R.sha(DENSE_BODY.encode()),
                    rectangular_attention=rectangular_attention)
    return text, identity


def generate_and_compile(root: Path, output: Path, shape: dict | None = None, *,
                         rectangular_attention: bool = False) -> tuple[dict, dict]:
    """Compile once; default layout has MAX_TOKENS=128 for both actual runs."""
    R.require(not output.exists(), 'refuse existing generated directory')
    text, provenance = resident_source(root, rectangular_attention=rectangular_attention)
    layout = R.make_layout(shape)
    R.require(layout['hidden'] <= 1536, 'hidden dimension exceeds resident A capacity')
    if rectangular_attention:
        R.require(layout['head_dim']<=128 and layout['heads']<=12,
                  'rectangular Attention shape exceeds fixed allocation')
    output.mkdir(parents=True)
    (output/'software_recipe.cpp').write_text(text)
    (output/'block_layout.h').write_text(R.header(layout))
    (output/'layout.json').write_text(json.dumps(layout, indent=2)+'\n')
    compiler = shutil.which('g++')
    R.require(compiler is not None, 'ordinary g++ compiler required')
    command = [compiler, *R.FLAGS, str(output/'software_recipe.cpp'), '-o', str(output/'software_recipe')]
    build = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (output/'build.log').write_text(build.stdout+build.stderr)
    R.require(build.returncode == 0, 'resident compile failed; see build.log')
    provenance.update(compile_command=command,
        compiler_version=subprocess.run([compiler, '--version'], check=True, capture_output=True, text=True).stdout.splitlines()[0],
        generated_cpp_sha256=R.file_sha(output/'software_recipe.cpp'),
        generated_header_sha256=R.file_sha(output/'block_layout.h'),
        binary_sha256=R.file_sha(output/'software_recipe'), generator_sha256=R.file_sha(Path(__file__)),
        status=STATUS, mapping=MAPPING, numerical_contract='qwen2-functional-bf16-fp32-ordered-v1',
        rounding_mode='FE_TONEAREST', hardware_simulation=False, generated_by_chisel=False)
    (output/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    return layout, provenance


def validate_generated(root: Path, generated: Path) -> tuple[dict, dict]:
    """Reuse an intact binary, source, layout, compiler contract, and generator."""
    layout = json.loads((generated/'layout.json').read_text())
    provenance = json.loads((generated/'provenance.json').read_text())
    source, identity = resident_source(root, rectangular_attention=provenance.get('rectangular_attention', False))
    R.require(layout == R.make_layout({key: layout[key] for key in R.SHAPE}), 'generated layout changed')
    for key, value in identity.items():
        # A later commit may contain unchanged guarded source; no new arithmetic.
        if key != 'git_head':
            R.require(provenance.get(key) == value, 'generated source identity differs: '+key)
    R.require(provenance['generated_cpp_sha256'] == R.sha(source.encode()) == R.file_sha(generated/'software_recipe.cpp'),
              'generated resident C++ changed')
    R.require(provenance['generated_header_sha256'] == R.sha(R.header(layout).encode()) == R.file_sha(generated/'block_layout.h'),
              'generated resident header changed')
    R.require(provenance['binary_sha256'] == R.file_sha(generated/'software_recipe'), 'resident binary changed')
    R.require(provenance['generator_sha256'] == R.file_sha(Path(__file__)), 'resident generator changed')
    R.require(provenance['compile_command'][1:5] == R.FLAGS and provenance['status'] == STATUS,
              'resident compiler flags/status changed')
    return layout, provenance


def expected_dense(tokens: int, k: int, n: int) -> dict:
    full = k <= 1536
    slots = 1 if full else 3
    kt, nt, mt = (k+255)//256, (n+255)//256, (tokens+15)//16
    groups = (nt+slots-1)//slots
    return dict(tokens=tokens, k=k, n=n, full_a=int(full), c_slots=slots,
        c_base_word=(k if full else 256)//2, scratch_bytes=768*1024,
        contexts_peak=min(5, mt), fifo_peak=1, final_peak=1,
        external_a_fp32_bytes=tokens*k*4*(1 if full else groups),
        logical_weight_bf16_bytes=k*n*2, external_d_fp32_bytes=tokens*n*4,
        prefix_restore_fp32_bytes=tokens*n*4*(kt-1), prefix_store_fp32_bytes=tokens*n*4*(kt-1),
        seed_contexts=mt*nt*(kt-1), snapshot_contexts=mt*nt*(kt-1),
        wide_issues=mt*nt*k, useful_macs=tokens*k*n, captures=mt*nt*kt, status=STATUS)


def parse_dense_log(log: str, layout: dict, tokens: int) -> list[dict]:
    rows = []
    for line in log.splitlines():
        if line.startswith('RESIDENT_DENSE '):
            row = dict(re.findall(r'(\w+)=([^ ]+)', line))
            rows.append({key: value if key == 'status' else int(value) for key, value in row.items()})
    h, f, kv = layout['hidden'], layout['ffn'], layout['kv_heads']*layout['head_dim']
    expected = [expected_dense(tokens, k, n) for k, n in ((h,h),(h,kv),(h,kv),(h,h),(h,f),(h,f),(f,h))]
    R.require(rows == expected, 'resident Dense counters/order differ from bounded mapping')
    return rows


def expected_attention(tokens: int, layout: dict) -> dict:
    return NUMERIC_ATT.expected(tokens, layout, ATT)


def parse_attention_log(log: str, layout: dict, tokens: int, enabled: bool) -> list[dict]:
    rows = []
    for line in log.splitlines():
        if line.startswith('RESIDENT_ATTENTION '):
            row = dict(re.findall(r'(\w+)=([^ ]+)', line))
            rows.append({key: value if key == 'status' else int(value) for key, value in row.items()})
    R.require(rows == ([expected_attention(tokens, layout)] if enabled else []),
              'resident Attention counters/order differ from bounded mapping')
    return rows


def _verify_m16(directory: Path, generated: Path, provenance: dict, arena_sha256: str) -> dict:
    result_path = directory/'RESULT.json'
    result = json.loads(result_path.read_text())
    R.require(result['status'] == STATUS and result['shape'] == dict(R.SHAPE, tokens=16)
              and result['completion_status'] == 'ALL_15_SOFTWARE_STAGES_COMPLETE',
              'actual M128 requires a completed resident M16 prerequisite')
    R.require(result['source_identity'] == provenance and Path(result['generated_directory']).resolve() == generated.resolve(),
              'M16 prerequisite must reuse the same generated binary/layout')
    R.require(result['readonly_sha256'] == arena_sha256, 'M16 prerequisite must use the same sealed arena')
    R.require(R.file_sha(directory/'run.log') == result['run_log_sha256'], 'M16 prerequisite log changed')
    log = (directory/'run.log').read_text()
    R.require(log.count('SOFTWARE_FLOAT_ENV ') == 1 and 'rounding=FE_TONEAREST probes=10' in log
              and log.count('SOFTWARE_RECIPE_STAGE ') == 15
              and 'SOFTWARE_RECIPE_COMPLETE tokens=16 stages=15' in log,
              'M16 prerequisite execution/environment incomplete')
    layout = R.make_layout()
    parse_dense_log(log, layout, 16)
    parse_attention_log(log, layout, 16, provenance.get('rectangular_attention', False))
    R.require([entry['name'] for entry in result['stages']] == list(R.STAGE_NAMES), 'M16 prerequisite stages missing')
    for phase, entry in enumerate(result['stages']):
        name = R.STAGE_NAMES[phase]
        width = next(r['words']//128 for r in layout['regions'] if r['name'] == name)
        R.require(entry['phase'] == phase and entry['width'] == width
                  and entry['path'] == f'phase_{phase}_{name}_recipe.f32le',
                  'M16 prerequisite stage identity changed')
        path = directory/entry['path']
        R.require(path.stat().st_size == 16*entry['width']*4 and R.file_sha(path) == entry['sha256'],
                  'M16 prerequisite stage changed')
        R.require(bool(R.np.isfinite(R.np.fromfile(path, dtype='<f4')).all()), 'M16 prerequisite nonfinite stage')
    return dict(directory=str(directory.resolve()), result_sha256=R.file_sha(result_path), status=STATUS)


def execute(root: Path, generated: Path, arena: Path, tokens: int, output: Path, *,
            expected_arena_sha256: str, timeout_seconds: float = 600,
            m16_prerequisite: Path | None = None) -> dict:
    """Run existing 15-stage driver from a caller-verified arena; never acquire data.

    Actual M16 and M128 use one max128 binary AND the same max128 readonly arena.
    Passing this model proves neither native accuracy nor hardware acceptance.
    """
    layout, provenance = validate_generated(root, generated)
    R.require(0 < tokens <= layout['max_tokens'], 'tokens outside generated capacity')
    actual_shape = {key: layout[key] for key in R.SHAPE} == R.SHAPE
    R.require(not actual_shape or tokens in (16, 128), 'actual model supports only M16/M128')
    R.require(0 < timeout_seconds <= 600, 'local run timeout must be in (0,600] seconds')
    R.require(tokens != 128 or not actual_shape or m16_prerequisite is not None,
              'actual M128 requires a completed resident M16 prerequisite')
    R.require(not output.exists(), 'refuse existing resident run directory')
    R.require(arena.stat().st_size == layout['writable_start'], 'readonly arena length mismatch')
    R.require(R.file_sha(arena) == expected_arena_sha256, 'sealed readonly arena SHA mismatch')
    prerequisite = _verify_m16(m16_prerequisite, generated, provenance, expected_arena_sha256) if actual_shape and tokens == 128 else None
    output.mkdir(parents=True)
    elapsed = R.execute(generated, arena, tokens, output, timeout_seconds)
    R.require(R.file_sha(arena) == expected_arena_sha256, 'sealed readonly arena changed during execution')
    log = (output/'run.log').read_text()
    dense = parse_dense_log(log, layout, tokens)
    attention_enabled = provenance.get('rectangular_attention', False)
    attention = parse_attention_log(log, layout, tokens, attention_enabled)
    stages = []
    for phase, name in enumerate(R.STAGE_NAMES):
        path = output/f'phase_{phase}_{name}_recipe.f32le'
        width = next(r['words']//layout['max_tokens'] for r in layout['regions'] if r['name'] == name)
        R.require(path.stat().st_size == tokens*width*4, 'resident stage length mismatch')
        stages.append(dict(phase=phase, name=name, width=width, path=path.name, sha256=R.file_sha(path)))
    result = dict(schema=1, status=STATUS, diagnostic_only=True,
        completion_status='ALL_15_SOFTWARE_STAGES_COMPLETE', mapping=MAPPING,
        shape={**{key: layout[key] for key in R.SHAPE}, 'tokens': tokens},
        readonly_sha256=expected_arena_sha256, generated_directory=str(generated.resolve()),
        source_identity=provenance, run_log_sha256=R.file_sha(output/'run.log'),
        stages=stages, dense=dense, attention=attention, wall_seconds=elapsed, m16_prerequisite=prerequisite,
        wall_seconds_purpose='CPU execution bookkeeping only; not performance, scalar timing or hardware cycles',
        scope=dict(software_only=True, consumes_own_previous_stages=True, all_15_stages=True,
                   sram_numerical_address_model=True, rtl_executed=False, hardware_cycles=None,
                   checkpoint_accuracy_signoff=False, hardware_acceptance=False,
                   official_framework_forward=False, accumulator_seed_interface_implemented=False,
                   physical_sram_repartition_implemented=False, host_command_execution=False,
                   real_idma_execution=False, ack_or_port_timing_validation=False,
                   rectangular_attention_numerical_address_model=attention_enabled,
                   attention_row_final_capture_route_implemented=False,
                   attention_scratch_gather_route_implemented=False,
                   other_operators='unchanged canonical software recipe'),
        weight_transport='logical BF16 byte counts; input arena is expanded FP32 fixture, not BF16 DDR or iDMA execution',
        bias_scope='canonical 15-stage driver fuses bias at Dense final emit; separate Host bias owner/transport is not executed',
        arithmetic='unchanged v0 BF16 operands, increasing-K FP32 std::fma prefixes, FP32 snapshots, bias once at final K',
        attention_arithmetic=('16 independent j%16 FP32 FMA stripes, ordered stripe 0..15 FP32 reduction, '
            'unchanged causal scalar softmax, BF16 probability and V, ascending-key FP32 PV; '
            'each row captured at its causal final key before physical inactive-row suffix updates'
            if attention_enabled else 'unchanged canonical software Attention'),
        attention_memory_accounting=('numeric_* byte counters are actual scalar C++ SRAM dereferences, including '
            'repeated per-lane operand reads; event_gather_bank_read_bytes counts published gather requests '
            'and is not executed RTL traffic or a timing measurement'))
    (output/'RESULT.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--output', required=True, type=Path)
    prepare.add_argument('--rectangular-attention', action='store_true',
                         help='also map canonical Attention into the fixed resident SRAM (diagnostic only)')
    run = sub.add_parser('execute')
    run.add_argument('--generated', required=True, type=Path)
    run.add_argument('--arena', required=True, type=Path)
    run.add_argument('--arena-sha256', required=True)
    run.add_argument('--tokens', required=True, type=int, choices=(16,128))
    run.add_argument('--output', required=True, type=Path)
    run.add_argument('--m16-prerequisite', type=Path)
    run.add_argument('--timeout-seconds', type=float, default=600)
    args = parser.parse_args()
    if args.command == 'prepare':
        _, result = generate_and_compile(ROOT, args.output, rectangular_attention=args.rectangular_attention)
    else:
        result = execute(ROOT, args.generated, args.arena, args.tokens, args.output,
            expected_arena_sha256=args.arena_sha256, timeout_seconds=args.timeout_seconds,
            m16_prerequisite=args.m16_prerequisite)
    print(json.dumps(dict(status=STATUS, output=str(args.output), binary_sha256=result.get('binary_sha256', result.get('source_identity', {}).get('binary_sha256')))))


if __name__ == '__main__':
    main()
