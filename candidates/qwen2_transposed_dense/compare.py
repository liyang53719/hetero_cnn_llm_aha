#!/usr/bin/env python3
"""Bounded MODEL-ONLY transposed Dense comparison; no official tensors/RTL."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


D = module('qwen2_dense_residency_numeric')
R = D.R
R.require(__debug__,'optimized Python (-O) is unsupported; validation assertions are required')
S = module('qwen2_prefill_resource_schedule')
ALGORITHM_SHA256='5db5c1d071d87a6601200706bb709be486235d6bd8671d3018eb792d42dbce6e'
SMALL_CASES_SHA256='331b4ee38b044766fdbce8bc8b9235bfff53ca356eb762fb6c4d9f95297a82e9'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_algorithm_sources():
    R.require(sha(HERE/'transposed_dense.inc.cpp')==ALGORITHM_SHA256,
              'reviewed Dense algorithm changed; re-review and re-bind explicitly')
    R.require(sha(HERE/'small_tests.inc.cpp')==SMALL_CASES_SHA256,
              'reviewed small cases changed; re-review and re-bind explicitly')


def output_directory(path):
    path=Path(path).resolve()
    R.require(path!=HERE and HERE not in path.parents,'outputs must be outside candidate source directory')
    R.require(not path.exists(),'refuse to overwrite evidence directory')
    return path


def activation_address(m,k):
    R.require(type(m) is int and type(k) is int and 0<=m<128 and 0<=k<2752,'A address out of fixed capacity')
    return (k%16)^(m//16),(k//16)*8+m//16,m%16


def weight_address(half,k,n):
    R.require(all(type(x) is int for x in (half,k,n)) and 0<=half<2 and 0<=k<128 and 0<=n<160,'B address out of fixed capacity')
    linear=half*1280+k*10+n//16
    return linear%16,linear//16,n%16


def address_proof():
    cases = []
    for depth in (16,256,1536,2048,2560,2752):
        occupied=set()
        for m in range(128):
            for k in range(depth):
                mt=m//16
                bank,word,lane=activation_address(m,k)
                assert 0<=bank<16 and 0<=word<1376 and 0<=lane<16
                address=(bank,word,lane)
                assert address not in occupied
                occupied.add(address)
                inverse=(16*(word%8)+lane,16*(word//8)+(bank^(word%8)))
                assert inverse==(m,k)
        for k in range(depth):
            gather=[((k%16)^mt,(k//16)*8+mt) for mt in range(8)]
            assert len({b for b,w in gather})==8
            assert all(8*(k//16)+(b^(k%16))==w for b,w in gather)
        for m in range(128):
            for base in range(0,depth,16):
                targets=[((k%16)^(m//16),(k//16)*8+m//16,m%16) for k in range(base,base+16)]
                assert len({b for b,w,l in targets})==16
                assert len({w for b,w,l in targets})==1 and len({l for b,w,l in targets})==1
        cases.append(dict(m=128,k=depth,unique_halfwords=len(occupied),payload_bytes=len(occupied)*2,
                          words_per_bank=depth//2,compute_max_reads_per_bank=1,
                          fp32_beat_scatter_max_writes_per_bank=1))
    # Native BF16 row beats contain 32 successive K: two addresses per bank.
    native=[((k%16)^7,(k//16)*8+7,15) for k in range(32)]
    assert len(set(native))==32 and all(sum(b==bank for b,w,l in native)==2 for bank in range(16))
    b_words=set()
    for half in range(2):
        for k in range(128):
            for n16 in range(10):
                linear=half*1280+k*10+n16
                bank,word,_=weight_address(half,k,n16*16)
                assert bank<16 and word<160 and (bank,word) not in b_words
                b_words.add((bank,word))
            for ctx in range(5):
                pair=[(half*1280+k*10+2*ctx+j)%16 for j in range(2)]
                assert len(set(pair))==2
    assert len(b_words)==16*160
    return dict(cases=cases,inverse='mt=word%8; m=16*mt+lane; k=16*(word//8)+(bank XOR mt)',
                full_down_required_words_per_bank=8960//2,full_down_required_bytes=128*8960*2,
                full_down_fits=False,native_bf16_beat_min_bank_write_phases=2,
                native_bf16_ingress_numerically_executed=False,
                b_bijection_words=len(b_words),b_bytes=len(b_words)*32,
                b_two_word_compute_and_refill_banks_distinct=True,
                same_address_read_broadcast_is_insufficient=True,
                exhaustive_allocation_and_port_set_checks=True)


def dense_plan(name,k,n):
    old=D.expected_dense(128,k,n)
    groups=(n+159)//160
    a=128*k*4*(1 if k<=2560 else groups)
    weight=k*n*2
    out=128*n*4
    beats=a//64
    issues=k*(n//32)
    old_segments=128*(n//256)
    new_segments=128*(n//32)
    contexts=[min(5,n//32-i) for i in range(0,n//32,5)]
    return dict(owner=name,k=k,n=n,n160_groups=groups,context_groups=contexts,
                a_chunk=2560,a_chunks_per_group=(k+2559)//2560,weight_chunk=128,
                a_full_k_resident=k<=2560,a_reads=1 if k<=2560 else groups,
                old_activation_bytes=old['external_a_fp32_bytes'],activation_bytes=a,
                activation_delta_bytes=a-old['external_a_fp32_bytes'],weight_bytes=weight,output_bytes=out,
                old_prefix_restore_bytes=old['prefix_restore_fp32_bytes'],
                old_prefix_store_bytes=old['prefix_store_fp32_bytes'],
                prefix_restore_bytes=0,prefix_store_bytes=0,wide_issues=issues,
                activation_ddr_beats=beats,activation_scatter_bank_word_writes=beats*16,
                masked_serial_refill_phases=beats*2,rmw_serial_refill_phases=beats*3,
                rmw_bank_word_reads=beats*16,
                old_output_row_segments=old_segments,output_row_segments=new_segments,
                old_fp32_beats_per_output_row_segment=16,fp32_beats_per_output_row_segment=2,
                output_write_descriptors_if_row_segments_not_coalesced=new_segments,
                descriptor_condition='burstWrites=true, aligned rows, original N256 row writer; with single-beat writes both mappings already issue184320 payload requests across all Dense',
                weight_row_segments=k*groups,old_weight_row_segments=k*(n//256),
                activation_row_segments=128*(1 if k<=2560 else groups*((k+2559)//2560)),
                operand_ready_issue_span_without_refills=sum((k-1)*5+c for c in contexts),
                operand_ready_context_hazard_bubbles_without_refills=sum((k-1)*(5-c) for c in contexts),
                context_hazard_note='Five-cycle source leaf recurrence with same-cycle completion bypass. Three-context tails insert gaps; actual refill waits can absorb some gaps, so do not add this column blindly to refill phases.',
                model_only=True)


def traffic():
    # Reuse all nineteen existing owner's event bodies and finite successful-path
    # accounting. Do not call report() with historical pins from an older commit.
    # Pin the files actually used below, and replace only seven Dense byte counts.
    original=S.Scheduler(dense_mapping='resident_m128_nc3').run(
        S.iter_events(128,5,'resident_m128_nc3'),require_terminal=True)
    assert len(original['completed_owners'])==19
    plans=[dense_plan(name,k,n) for name,k,n in S.BOUND.MATRICES]
    lookup={p['owner']:p for p in plans}
    owners=[]
    for owner in original['completed_owners']:
        metrics=original['stage_metrics'][owner]
        old_r,old_w=metrics.get('external_read_bytes',0),metrics.get('external_write_bytes',0)
        p=lookup.get(owner)
        if p:
            assert old_r==p['old_activation_bytes']+p['weight_bytes'] and old_w==p['output_bytes']
        read=p['activation_bytes']+p['weight_bytes'] if p else old_r
        owners.append(dict(owner=owner,old_read_bytes=old_r,read_bytes=read,
                           write_bytes=old_w,delta_bytes=read-old_r,
                           read_write_64b_transfers=(read+old_w)//64))
    def summed(field): return sum(p[field] for p in plans)
    total_read=sum(o['read_bytes'] for o in owners)
    total_write=sum(o['write_bytes'] for o in owners)
    total_beats=sum(o['read_write_64b_transfers'] for o in owners)
    macs=original['metrics']['useful_macs']
    restore=summed('old_prefix_restore_bytes')
    assert restore==81788928 and total_read==164888576 and total_write==22544384
    assert total_beats==2928640 and summed('wide_issues')==1462272
    # Analytic down-only alternative: existing A depth permits K2560 chunks,
    # sweep N groups before next K chunk and save every incomplete physical C
    # tile to a separate DDR region. This is NOT executed by the C++ model.
    down=lookup['down']
    prefix_plane=128*1536*4
    partial_bytes=prefix_plane*((8960+2559)//2560-1)
    assert partial_bytes==2359296
    spill_read=total_read-down['activation_bytes']+128*8960*4+partial_bytes
    spill_write=total_write+partial_bytes
    analytic_alternative=dict(status='ANALYTIC_ONLY_NOT_EXECUTED',
        mapping='six full-K transposed Dense; down K2560 outer loop with physical FP32 C in DDR',
        down_k_chunks=[2560,2560,2560,1280],down_a_reads=1,
        a_sram_bytes=704512,b_sram_bytes=81920,scratch_bytes=786432,
        down_contexts=48,physical_tile_bytes=16384,prefix_ddr_region_bytes=prefix_plane,
        prefix_ddr_layout='separate 64-byte-aligned region: base + n32_context*16384 + physical_row*1024 + physical_col*4',
        prefix_identity='(down owner, N32 context index, exact increasing-K prefix end); write ACK before tile reuse/read; final output only at K8960',
        prefix_store_bytes=partial_bytes,prefix_restore_bytes=partial_bytes,
        prefix_64b_restore_beats=partial_bytes//64,
        hypothetical_four_phase_restore_subtotal=partial_bytes//64*4,
        restore_subtotal_condition='ONLY an assumed four-cycle/64B delivery scenario; existing SRAM reader does not read DDR. Not a source-bound timing result for this route.',
        full_graph_read_bytes=spill_read,full_graph_write_bytes=spill_write,
        full_graph_bytes=spill_read+spill_write,full_graph_64b_transfers=(spill_read+spill_write)//64,
        bytes_saved_vs_all_transposed=total_read+total_write-spill_read-spill_write,
        bytes_added_vs_old_resident=spill_read+spill_write-(total_read-summed('activation_delta_bytes')+total_write),
        interfaces_unimplemented=['physical-tile prefix DDR writer with ACK lifetime and identity',
            'DDR response to bounded 64B seed staging and retained leaf exact-FP32 seed port',
            'error, cancellation, stall and partial-prefix transaction handling'],
        extra_capacity='786432-byte dedicated DDR allocation, not on-chip SRAM; minimum one 64B seed payload hold plus metadata must be explicitly allocated, never an invisible tile cache')
    return dict(dense=plans,owners=owners,down_ddr_prefix_alternative=analytic_alternative,
        totals=dict(old_dense_activation_bytes=summed('old_activation_bytes'),
            dense_activation_bytes=summed('activation_bytes'),dense_weight_bytes=summed('weight_bytes'),
            dense_output_bytes=summed('output_bytes'),activation_delta_bytes=summed('activation_delta_bytes'),
            read_bytes=total_read,write_bytes=total_write,read_write_bytes=total_read+total_write,
            read_write_64b_transfers=total_beats,old_read_bytes=sum(o['old_read_bytes'] for o in owners),
            removed_prefix_restore_bytes=restore,removed_prefix_store_bytes=summed('old_prefix_store_bytes'),
            old_seed_64b_beats=restore//64,old_seed_source_four_phase_cycles=restore//64*4,
            dense_wide_issues=summed('wide_issues'),useful_full_graph_macs=macs,
            masked_serial_refill_phases=summed('masked_serial_refill_phases'),
            rmw_serial_refill_phases=summed('rmw_serial_refill_phases'),
            rmw_refill_plus_dense_issue_serial_subtotal=summed('rmw_serial_refill_phases')+summed('wide_issues'),
            old_output_row_segments=summed('old_output_row_segments'),output_row_segments=summed('output_row_segments'),
            old_weight_row_segments=summed('old_weight_row_segments'),weight_row_segments=summed('weight_row_segments')),
        shared_idma_conditional_bound=dict(cycles_at_least=total_beats,
            useful_4096mac_utilization_at_most=macs/(4096*total_beats),
            condition='existing event model has one serialized idma read/write transaction resource; 64 B/cycle ideal service',
            physical_absolute_bound=False,full_cycle_prediction=False),
        notes=['Only successful-path tensor/parameter transport of the original 19 owners is counted.',
            '21 public commands remain; q/k/v bias are separate owners in this ledger, not fused away.',
            'Command/tensor/policy/descriptor fetch bytes, burst legalization, memory and ACK latency are unresolved.',
            'No cross-owner forwarding, full weight cache or overlap credit.',
            'Output row segments assume the unchanged one finalValue plus two result slots; no extra coalescing tile.',
            'All traffic values are analytic event counts. The small C++ test executes no DDR/Host command.'])


def resource_ledger():
    attention=S.ATT.scratch_layout(128,5)
    assert attention['used_a_bytes']<=704512 and attention['used_b_bytes']<=81920
    return dict(scratch=dict(a_banks=16,a_words_per_bank=1376,a_word_bits=256,a_bytes=704512,
                    b_banks=16,b_words_per_bank=160,b_word_bits=256,b_bytes=81920,total_bytes=786432,
                    production_partition_unchanged='existing 688 KiB A + 80 KiB B retained; only layout/routing changes'),
        reused_rectangular_attention=dict(used_a_bytes=attention['used_a_bytes'],used_b_bytes=attention['used_b_bytes'],fits_same_partition=True),
        payloads=dict(fma_lanes=4096,slices=8,rows_per_slice=16,cols_per_slice=32,
            fp32_contexts=5,fp32_context_bytes=81920,metadata_entries=8,result_fifo_entries=2,
            result_fifo_bytes=32768,final_value_entries=1,final_value_bytes=16384,
            existing_leaf_result_register_slots=5,existing_leaf_result_register_bytes=81920,
            leaf_result_registers_note='Existing retained leaf pipeline result registers remain. C++ does not simulate these five stages; its arrays are not a complete hardware payload inventory.',
            refill_hold_bf16_bytes=32,rmw_optional_stall_response_hold_bytes=512),
        activation_gather=dict(ports='one read per each of eight distinct A banks per issue; no extra per-bank port',
            address='bank=(k%16) XOR mt; word=(k//16)*8+mt; lane=m%16',
            route='eight bank words permuted to M order, then M128 duplicated into two sets of four B32 slice operands',
            missing='current same-address A reads and A16 scalar selectors do not implement this gather'),
        weight_layout=dict(linear_word='half*1280 + kWithin128*10 + nWithin160//16',bank='linear_word%16',word='linear_word//16',lane='nWithin160%16',
            live_bytes=40960,reserved_two_halves_bytes=81920,allocated_bytes=81920,
            compute_reads='two 256-bit words from two distinct B banks per N32 context issue',
            refill='one BF16 64B DDR beat writes two full 256-bit words; no masking required for official N multiple32',
            capacity_note='all16 banks exactly160words; each half80words/bank. Numeric model alternates both halves serially; no prefetch overlap credited'),
        masked_refill=dict(phases=['accept FP32 DDR beat and latch16 RNE BF16 results',
                                  'write one16-bit lane in each of16 independent banks'],
            bank_word_writes_per_fp32_beat=16,new_halfword_masks=True,
            implementation_missing='16 independently enabled bank write routes and a real16-bit mask-capable SRAM interface'),
        rmw_refill=dict(phases=['accept FP32 DDR beat and latch256-bit conversion',
                               'read one old256-bit word from each of16 banks at common word address',
                               'merge common lane with permuted held16-bit values and write16 full words'],
            bank_word_reads_per_fp32_beat=16,bank_word_writes_per_fp32_beat=16,
            control='held word11 bits, lane4 bits, row-tile3 bits, valid/phase plus256-bit converted payload; synchronous responses consumed at guaranteed next write edge',
            masked_sram_required=False,additional_per_bank_ports=0,
            simultaneous_read_compute=False,
            first_lane_initializes_word=True,publish_only_after_all_rows_and_refill_commit=True,
            implementation_missing='16-bank write enables/data muxes/fanout, read ownership arbitration and synchronous response lifetime; existing DMA selects only one bank',
            stall_contract='do not issue RMW reads unless every following write can commit; otherwise allocate explicit4096-bit response hold',
            pipelining='not credited: 1R+1W could permit overlapping adjacent RMW beats with hazard proof, refill still conflicts with compute reads'),
        output_route=dict(formula='Y[m,nWithin32] = finalValue[physical_row=n%16][physical_col=32*(m//32+4*(n//16))+m%32]',
            fp32_beat='16 different physical rows, one common physical column, gathered into one512-bit output beat',
            extra_transpose_tile=False,missing='output mux/address/row width/control changes; current same-row16-column selector is insufficient'),
        operand_route=dict(requirement='two distinct A16 weight groups, each routed to four slices; existing service broadcasts the same A16 to all8',
            naive_bus_expansion_bits=256,area_timing_free=False,
            optional_no_bus_growth='pack second weight16 into otherwise duplicate b[128:143], retain first128 unique activations, and decode/duplicate inside service; mode, mux and routes still unimplemented'),
        scheduling=dict(refill_compute_serialized=True,physical_context_reuse_cycles_at_least=5,
            numerical_model_metadata_peak=1,numerical_model_result_peak=1,
            hardware_cycle_prediction=None,throughput_or_area_signoff=False))


def numeric(output: Path, *, tiny=False):
    verify_algorithm_sources()
    helpers,maths,identity=D.frozen_sources(ROOT)
    canonical=R.section(maths,'  void dense(','  void rope(')
    assert R.sha(canonical.encode())=='40c21155585668fd85ceb7aa0556e985667ae133d95f6f9dfdae022583bff38d'
    generated=output/'generated'
    generated.mkdir(parents=True,exist_ok=False)
    harness='''\nclass Harness { public:
  std::vector<float> reference; unsigned tokens;
  Harness(unsigned m,size_t words):reference(words,fp(0x7fc00001u)),tokens(m){}
  float get(uint64_t off,size_t i)const{return reference.at(off/4+i);}
  void put(uint64_t off,size_t i,float x){reference.at(off/4+i)=x;}
'''
    cases=(HERE/'small_tests.inc.cpp').read_text()
    if tiny:
        cases=cases[:cases.index('int main()')]+'''int main(){try{
          verifyFloatEnvironment();oneCase(128,16,48,16,0,true);
          std::cout<<"TINY_COMPARISON_PASS cases=1 mapped_runs=2 official_forward=0"<<std::endl;return 0;
        }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}\n'''
    source=helpers+R.HOST_PROBES+harness+canonical+(HERE/'transposed_dense.inc.cpp').read_text()+cases
    (generated/'small_comparison.cpp').write_text(source)
    (generated/'block_layout.h').write_text(R.header(R.make_layout()))
    binary=generated/'small_comparison'
    command=[shutil.which('g++'),*R.FLAGS,str(generated/'small_comparison.cpp'),'-o',str(binary)]
    build=subprocess.run(command,capture_output=True,text=True,timeout=90)
    (generated/'build.log').write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stderr
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    # Bind one actual process to one allowed CPU; no multicore throughput claim.
    cpu=min(os.sched_getaffinity(0))
    run=subprocess.run(['taskset','-c',str(cpu),str(binary)],env=env,capture_output=True,text=True,timeout=90)
    (generated/'run.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0,run.stdout+run.stderr
    marker=('TINY_COMPARISON_PASS cases=1 mapped_runs=2 official_forward=0' if tiny else
            'SMALL_COMPARISON_PASS cases=10 mapped_runs=20 official_forward=0 official_m128_numeric=0 synthetic_m128=1')
    assert marker in run.stdout
    cases=[]
    for line in run.stdout.splitlines():
        if line.startswith('BIT_EXACT '): cases.append({k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)})
    return dict(source_identity=identity,canonical_dense_sha256=R.sha(canonical.encode()),
        compiler_command=command,compiler_version=subprocess.run([command[0],'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],
        strict_flags=R.FLAGS,single_cpu=cpu,generated_cpp_sha256=sha(generated/'small_comparison.cpp'),
        binary_sha256=sha(binary),log_sha256=sha(generated/'run.log'),cases=cases,
        coverage='packaging_tiny_only' if tiny else 'bounded_full_small_suite',
        mapped_runs=2 if tiny else 20,bit_mismatches=0,checked_values=sum(c['values'] for c in cases)*2,
        exhaustive_bf16_values_in_swap_probe=0 if tiny else 65280,swap_probe_triplets=0 if tiny else 65280*10*8,
        error_rejections=0 if tiny else 18,arithmetic_rewrite_negative_controls=0 if tiny else 2,
        official_model_run=False,official_forward=False,official_m128_numerical_run=False,synthetic_m128_numerical_run=True,
        full_finite_cartesian_domain_exhausted=False,rtl_or_protocol_execution=False)


def run(output: Path, *, tiny=False, analytic_only=False):
    R.require(not (tiny and analytic_only),'tiny and analytic-only are mutually exclusive')
    verify_algorithm_sources()
    output=output_directory(output)
    result=dict(status='MODEL_ONLY_DIAGNOSTIC_NOT_ACCEPTED',native_m128_gate='FAIL_BF16_STAGE_BUDGET_UNCHANGED',
        finite_domain='finite FP32 activation that RNE converts to finite BF16; exact finite BF16 weights; finite terminal FP32 accumulator and bias/output; no per-step flag propagation modeled',
        semantic_contract='original v0 +0 init, increasing K strict FP32 fma, unchanged FP32 prefix across loads, one terminal FP32 bias add, signed zeros/subnormals preserved',
        limits=['Synthetic M16/M32 plus bounded M128/K272/N192 tests only; no official M128 rerun.',
            'Errors are domain rejections, not a hardware fault status/timing or cancellation/drain proof.',
            'No masked writes, RMW routing, second A16 group, gather or output remap were implemented in RTL.',
            'No full hardware cycle prediction or area/frequency/80-percent claim.'],
        address_proof=address_proof(),resource_ledger=resource_ledger(),traffic=traffic(),
        numeric=None if analytic_only else numeric(output,tiny=tiny),numeric_executed=not analytic_only)
    if analytic_only:
        result['status']='MODEL_ONLY_ANALYTIC_NOT_EXECUTED'
        output.mkdir(parents=True)
    files=[Path(__file__),HERE/'transposed_dense.inc.cpp',HERE/'small_tests.inc.cpp',
        ROOT/'scripts/qwen2_dense_residency_numeric.py',ROOT/'scripts/qwen2_block_recipe_model.py',
        ROOT/'scripts/qwen2_prefill_resource_schedule.py',ROOT/'scripts/qwen2_prefill_traffic_bound.py',
        ROOT/'scripts/qwen2_rectangular_attention_model.py',
        ROOT/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/StreamingDense.scala',
        ROOT/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/MatrixPipeline.scala',
        ROOT/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/HostBlockTop.scala',
        ROOT/'chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala',
        ROOT/'rtl/integration/idma_backend_rw_axi_flat_wrap.sv',
        ROOT/'rtl/matrix/candidates/rev8b_b/bf16_context_scheduler5_rev8b_b_candidate.sv',
        ROOT/'rtl/matrix/candidates/rev8b_b/bf16_outer_product_array_control5_rev8b_b_candidate.sv',
        ROOT/'rtl/matrix/candidates/rev8b_b/bf16_context_fma_pipeline_lane5_rev8b_b_candidate.sv',
        ROOT/'reports/execution/QWEN2_DENSE_RESIDENCY_NUMERIC_20261011/SUMMARY.json',
        ROOT/'reports/execution/QWEN2_RESIDENT_SEED_FRONTEND_20261011/SUMMARY.json']
    result['source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in files}
    result['git_head']=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    result['packaging_provenance']=dict(algorithm_sha256=ALGORITHM_SHA256,
        executed_work_algorithm_sha256=ALGORITHM_SHA256,algorithm_bytes_equal=True,
        driver_refactored=True,old_driver_pass_rebound=False,
        meaning='The algorithm include matches the reviewed work file; this receipt records only the executions explicitly listed above.')
    (output/'SUMMARY.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--tiny',action='store_true',help='one tiny packaging check; skips full small suite and swap enumeration')
    mode.add_argument('--analytic-only',action='store_true',help='address/resource/19-owner ledger only; no C++ execution')
    args=parser.parse_args()
    result=run(args.out,tiny=args.tiny,analytic_only=args.analytic_only)
    numerical=result['numeric'] or {}
    print(json.dumps(dict(status=result['status'],mapped_runs=numerical.get('mapped_runs',0),
        checked_values=numerical.get('checked_values',0),traffic=result['traffic']['totals']),indent=2))


if __name__=='__main__': main()
