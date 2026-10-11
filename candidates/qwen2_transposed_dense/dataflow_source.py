"""Frozen fullgraph dataflow source construction within the transposed candidate.

The five include files are byte-identical to the reviewed work-only experiment.
The generated official-shaped C++ is also pinned; source identity is not a run.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent / 'dataflow'
CANDIDATE = HERE.parent
ROOT = CANDIDATE.parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

FC = module('dataflow_fullchain', CANDIDATE / 'full_chain.py')
C, D, R = FC.C, FC.D, FC.R
EXPECTED = '4ce29539e1bd7345d5ccee88c7d70b056ec39bdadae4df416ebb401b9afbdcc1'
CPP_SHA256 = '38a3a0169cf584d3aa7f6a6e8ad9766cbd2b150d8568c4ba5f600151dab66d39'
INCLUDE_SHA256 = {
    'transport.inc.cpp': 'c03a3a896bd9b3a511289ddc8b1c05f85ae18c90228615a77aa30f6a30ad57bf',
    'tile_storage.inc.cpp': 'a07b4411207526dbd019fb2778e2addb8503fb6ab100fd35e179f38b86b04c3e',
    'methods.inc.cpp': 'dd1a86099659959c5d481d22f9f0b3f618ce17baf998db684a73af9563ed2bc3',
    'small_tests.inc.cpp': '1a00b84f590defe68e868826168b02c38ee60d66aa6d4211af1404b5883d4468',
    'fullgraph_tests.inc.cpp': '498a08661db04f4687ad8de065095c9a689ed0a7a298870d798f3564a16824b7',
}
HISTORICAL_WORK = {
    'scope': 'previous work-only driver; no execution by the packaged driver implied',
    'result_sha256': '1c33cc1272bc6388f5da1f67da96fde5c2060fffb616d87dbc4f2a8da6f64bd1',
    'prepared_sha256': '15b5043a945589cb320319035eeba82a21cc2689fc91ca42ce6bf4b5894726cb',
    'builder_sha256': 'e42b50273b8076ba815787a215b049fa217a05ff3e4fecb1da959f586af63c1a',
    'generated_cpp_sha256': CPP_SHA256,
    'old_driver_pass_rebound': False,
}

def verify_algorithm_sources():
    C.verify_algorithm_sources()
    for name, expected in INCLUDE_SHA256.items():
        FC.checked_hash(HERE / name, expected)

def generated():
    verify_algorithm_sources()
    source, down, full, identity = _generated()
    R.require(R.sha(source.encode()) == CPP_SHA256, 'frozen fullgraph generated C++ changed')
    return source, down, full, identity

def _generated():
    original,identity=FC.new_source()
    assert R.sha(original.encode())==EXPECTED
    helpers,maths,base_identity=D.frozen_sources(ROOT)
    canonical=R.section(maths,'  void dense(','  void rope(')
    assert R.sha(canonical.encode())=='40c21155585668fd85ceb7aa0556e985667ae133d95f6f9dfdae022583bff38d'
    transposed=(C.HERE/'transposed_dense.inc.cpp').read_text()
    physical=R.section(transposed,'    struct Physical {','    static_assert(sizeof(Physical::a)')
    assert physical.endswith('    };\n')
    physical=physical[:-7]+(HERE/'tile_storage.inc.cpp').read_text()+'};\n'
    physical=physical.replace('struct Physical {','struct DataflowPhysical {').replace('      Physical() {','      DataflowPhysical() {')
    load=R.section(transposed,'    auto loadA=[&](int base,int depth) {','    if(full)loadA(0,K);')
    load=load[load.index('{')+1:load.rfind('    };')]
    issue=R.section(transposed,'        for(int kb=ab;kb<ab+ad;kb+=128) {','      for(int ctx=0;ctx<count;ctx++) {')
    # Extract the K-block loop, excluding the two enclosing ab/ng closing braces.
    assert issue.endswith('      }\n')
    issue=issue[:-8]
    assert issue.count('full?k:k-ab')==1
    issue=issue.replace('full?k:k-ab','k-aBase')
    support=(HERE/'transport.inc.cpp').read_text()+physical
    support+='''static_assert(sizeof(DataflowPhysical::a)==704512&&sizeof(DataflowPhysical::b)==81920,"fixed A/B");
static_assert(sizeof(DataflowPhysical::accum)==81920&&sizeof(DataflowPhysical::result)==32768&&sizeof(DataflowPhysical::finalValue)==16384,"fixed registers");
'''
    methods=(HERE/'methods.inc.cpp').read_text().replace('@@LOAD_A@@',load).replace('@@ISSUE_K@@',issue)
    assert '@@' not in methods
    src=original.replace('class SoftwareRecipe {',support+'\nclass SoftwareRecipe {')
    getter='  float get(uint64_t offset,size_t i)const{return reference.at(offset/4+i);}'
    replacement='''  void arithmeticAddress(uint64_t offset,size_t i)const{
    const uint64_t address=offset+uint64_t(i)*4;
    need(!((address>=OFF_GATE&&address<OFF_GATE+uint64_t(MAX_TOKENS)*F*4)||
           (address>=OFF_UP&&address<OFF_UP+uint64_t(MAX_TOKENS)*F*4)),"eliminated gate/up DDR arithmetic access");
  }
  float get(uint64_t offset,size_t i)const{arithmeticAddress(offset,i);return reference.at(offset/4+i);}'''
    assert src.count(getter)==1;src=src.replace(getter,replacement)
    setter='  void put(uint64_t offset,size_t i,float x){reference.at(offset/4+i)=x;}'
    assert src.count(setter)==1;src=src.replace(setter,'  void put(uint64_t offset,size_t i,float x){arithmeticAddress(offset,i);reference.at(offset/4+i)=x;}')
    src=src.replace('  void computeReference(){',methods+'\n  void computeReference(){')
    old='''norm(OFF_R,OFF_GAMMA1,OFF_N1);dense(OFF_N1,OFF_WG,OFF_GATE,H,F);dense(OFF_N1,OFF_WU,OFF_UP,H,F);
    for(size_t i=0;i<size_t(tokens)*F;i++){float g=get(OFF_GATE,i),e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);put(OFF_ACT,i,mul(mul(sig,g),get(OFF_UP,i)));}
    dense(OFF_ACT,OFF_WD,OFF_DOWN,F,H);'''
    assert src.count(old)==1
    src=src.replace(old,'norm(OFF_R,OFF_GAMMA1,OFF_N1);tiledFFN();\n    dataflowDown(OFF_ACT,OFF_WD,OFF_DOWN,F,H,-1,downChunk);')
    assert src.count('std::isfinite(model.get(s.off,i))')==1
    src=src.replace('std::isfinite(model.get(s.off,i))','std::isfinite(model.observationGet(s.off,i))')
    oldwrite='output.write(reinterpret_cast<const char*>(model.reference.data()+s.off/4),count*4);'
    assert src.count(oldwrite)==1
    src=src.replace(oldwrite,'for(size_t i=0;i<count;i++){const float v=model.observationGet(s.off,i);output.write(reinterpret_cast<const char*>(&v),4);}')
    oracle=R.section(original,'class SoftwareRecipe {','int main(')
    oracle=oracle.replace('SoftwareRecipe','OracleRecipe')
    frozen_dense=R.section(oracle,'  void dense(','  void rope(')
    oracle=oracle.replace(frozen_dense,canonical)
    harness='''class Harness { public:
      std::vector<float> reference; unsigned tokens;
      Harness(unsigned m,size_t words):reference(words,fp(0x7fc00001u)),tokens(m){}
      float get(uint64_t off,size_t i)const{return reference.at(off/4+i);}
      void put(uint64_t off,size_t i,float x){reference.at(off/4+i)=x;}
'''
    down=helpers+R.HOST_PROBES+support+harness+canonical+methods+'};\n'+(HERE/'small_tests.inc.cpp').read_text()
    full=src[:src.index('int main(')]+oracle+(HERE/'fullgraph_tests.inc.cpp').read_text()
    return src,down,full,dict(frozen_source_sha256=EXPECTED,base_recipe_identity=base_identity,
      fullchain_identity=identity,load_a_sha256=R.sha(load.encode()),k_loop_sha256=R.sha(issue.encode()),
      canonical_dense_sha256=R.sha(canonical.encode()),
      unchanged_attention_body_sha256=R.sha(D.NUMERIC_ATT.ATTENTION_BODY.encode()),
      changes=['K-outer down transport','FFN SRAM tile lifecycle','observer-only stage export and gate/up arithmetic guard'],
      not_implemented=['Host fused dispatch','real iDMA','Chisel/RTL','leaf pipeline/flags','route area/frequency'])
def traffic():
    old=C.traffic();owners=[]
    for row in old['owners']:
      row=dict(row);name=row['owner'];r=row['read_bytes'];w=row['write_bytes']
      if name=='down':r-=128*8960*4*9;r+=2359296;w+=2359296
      if name in ('gate','up'):w-=128*8960*4
      if name=='up':r-=128*1536*4
      if name=='silu':r-=2*128*8960*4
      row.update(read_bytes=r,write_bytes=w,delta_bytes=r+w-row['old_read_bytes']-row['write_bytes'],read_write_64b_transfers=(r+w)//64,
        count_source='actual_model_transfer_formula_synthetically_exercised' if name in ('q','k','v','o','gate','up','silu','down') else 'reused_source_event_count',
        packaged_driver_actual_m128_transfer_counter_verified=False)
      owners.append(row)
    r=sum(o['read_bytes'] for o in owners);w=sum(o['write_bytes'] for o in owners)
    assert (r,w,r+w)==(115998720,15728640,131727360),(r,w,[o['owner'] for o in owners])
    return dict(owners=owners,read_bytes=r,write_bytes=w,total_bytes=r+w,transfers_64b=(r+w)//64,
      saved_vs_all_transposed=old['totals']['read_write_bytes']-r-w,
      saved_vs_down_prefix_only=150863872-r-w,
      conditional_ideal_idma_utilization_bound=old['totals']['useful_full_graph_macs']/(4096*((r+w)//64)),
      logical_math_owners=19,old_public_host_commands=21,modified_host_dispatch_implemented=False,
      stage_observer_copy_bytes_excluded=2*128*8960*4,
      condition='Successful-path analytic byte ledger only. Same serialized shared ideal64B/cycle adapter. No cycle prediction or hardware utilization measurement.')
def resources():
    base=C.resource_ledger();base['prefix']=dict(ddr_bytes=786432,tile_bytes=16384,contexts=48,seed_payload_bytes=64,
      control='two64-bit ACK/read bitmaps; two64-bit current/in-flight job generations; eight32-bit owner/epoch/nextEpoch/context-count/in-flight owner/context/prefix-end/beat-count;4state flags; addresses derived',
      proposed_control_bits=4*64+8*32+4,control_rounded_bytes=65,
      admission_generation_bits=64,publication_control_bits=64+5*32+3,publication_control_rounded_bytes=29,control_implementation='proposed model-state accounting, not synthesized RTL')
    base['ffn']=dict(retained_input_bytes=393216,slot_bytes=81920,slots=3,a_reserved_bytes=638976,
      a_words_used_per_bank=1248,a_spare_bytes=65536,slot_metadata='three tags: ng32,cols32,rows32,stored32,read32,live1,complete1 plus sticky poison =487 bits rounded61B; host counters diagnostic only',
      b_bytes=81920,compute_and_transfer_serial=True,extra_sram_ports=0,
      scalar_read_write='One FP32 read/write uses one32-bit portion of one32-byte A word; operations serialized. Actual write mask or RMW route required; no free port/timing assumption.')
    base['observers']=dict(gate_up_max_bytes=9175040,arithmetic_read_allowed=False,allocation='host diagnostic heap only, excluded from modeled device; not hardware buffer')
    base['limits']=['one live physical scratch per owner; same fixed capacities reused','existing leaf internal result groups81920B unchanged and not C++ pipeline simulated','serial control checks are not RTL ACK/error/backpressure proof','fixed64B prefix payload is additional explicit staging; stall/route realization remains open','CPU duration not hardware throughput']
    return base
def address_checks():
    occupied=set()
    for m in range(128):
      for k in range(1536):occupied.add(C.activation_address(m,k))
    assert len(occupied)==128*1536
    slots=[]
    for slot in range(3):
      cells=set()
      for m in range(128):
        for n in range(160):
          bank,word,lane=m%16,768+slot*160+(m//16)*20+n//8,2*(n%8)
          assert word<1376
          for l in (lane,lane+1):
            addr=bank,word,l;assert addr not in occupied and addr not in cells;cells.add(addr)
      assert len(cells)==40960;occupied.update(cells);slots.append(dict(slot=slot,halfwords=len(cells)))
    assert len(occupied)*2==638976
    prefix={0x100000000+c*16384+b*64 for c in range(48) for b in range(256)}
    assert len(prefix)==12288 and max(prefix)+64-min(prefix)==786432
    return dict(ffn_unique_halfwords=len(occupied),ffn_reserved_bytes=len(occupied)*2,slots=slots,prefix_unique_beats=len(prefix),alias_free=True)
