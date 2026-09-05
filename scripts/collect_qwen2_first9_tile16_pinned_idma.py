#!/usr/bin/env python3
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];LOG=Path('work/results/qwen2_first9_tile16_pinned_idma/tb.log');COAL=Path('work/results/qwen2_pinned_idma_tile/tb.log')
m=re.search(r'QWEN2_FIRST9_TILE16_PINNED_IDMA_PASS commands=(\d+) rows=(\d+) descriptor_fetches=(\d+) abstract_dma=(\d+) flat_idma=(\d+) axi_read_beats=(\d+) axi_write_beats=(\d+) completions=(\d+) bf16_bit_exact=(\d+) matrix_steps=(\d+) rope_steps=(\d+) no_intermediate_injection=(\d+) upstream_clean=(\d+)',(ROOT/LOG).read_text());assert m and tuple(map(int,m.groups()))==(9,16,62,145,101432,104162,104162,9,118784,98304,1920,1,1);ct=(ROOT/COAL).read_text();assert 'QWEN2_PINNED_IDMA_TILE_PASS abstract_requests=8 flat_requests=2383' in ct and 'Error:' not in ct
idma=ROOT/'work/upstream/idma';assert subprocess.check_output(['git','-C',idma,'rev-parse','HEAD'],text=True).strip()=='2e0b0fe53b6f8823319e2428e2e9abc2db149b7d' and not subprocess.check_output(['git','-C',idma,'status','--porcelain'],text=True).strip()
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def fragment_metrics():
    match = re.search(r'FIRST9_FRAGMENT_COUNTERS wall_cycles=(\d+) matrix_steps=(\d+) useful_macs=(\d+) ddr_read_bytes=(\d+) ddr_write_bytes=(\d+)', (ROOT/LOG).read_text())
    assert match, 'missing actual fragment ROI counters'
    wall, steps, useful, read_bytes, write_bytes = map(int, match.groups())
    assert wall > 0 and steps == 98304 and useful == 16*1536*(1536+256+256)
    assert useful == steps*512 and read_bytes == 6477952 and write_bytes == 188416
    budget = re.search(r'DDR_BUDGET_COUNTERS read_bytes=(\d+) write_bytes=(\d+) read_throttle=(\d+) write_throttle=(\d+) clock_hz=800000000', (ROOT/LOG).read_text())
    assert budget, 'missing DDR bandwidth envelope counters'
    physical_read, physical_write, rstall, wstall = map(int, budget.groups())
    assert physical_read == read_bytes and physical_write == write_bytes
    log = (ROOT/LOG).read_text()
    op_pairs = re.findall(r'ROI_OPERATION index=(\d+) cycles=(\d+)', log)
    reason_pairs = re.findall(r'ROI_REASON index=(\d+) cycles=(\d+)', log)
    assert len(op_pairs) == 9 and len(reason_pairs) == 8
    operations = {int(i): int(c) for i, c in op_pairs}
    reasons = {int(i): int(c) for i, c in reason_pairs}
    assert set(operations) == set(range(9)) and set(reasons) == set(range(8))
    assert sum(operations.values()) == wall == sum(reasons.values())
    assert reasons[0] == steps
    op_names = ['RMSNorm', 'Q', 'Q_bias', 'Q_RoPE', 'K', 'K_bias', 'K_RoPE', 'V', 'V_bias']
    reason_names = ['matrix_accept', 'matrix_backpressure', 'l2_read_request_wait',
                    'l2_read_response_pending', 'l2_write_request_wait', 'dma_response_pending',
                    'descriptor_response_pending', 'other']
    return dict(evidence_class='numerical_RTL_first9_rows16_fragment',
                wall_cycles=wall, useful_macs=useful,
                useful_wall_mac_utilization=useful/(512*wall),
                clock_hz_for_conversion=800000000,
                converted_fragment_latency_seconds=wall/800000000,
                full_model_tokens_per_second=None,
                full_q1024_mac_utilization=None,
                memory_model='axi_sim_mem with 100/40GBps bandwidth envelope at800MHz; no DRAM bank/refresh/latency model',
                ddr_physical_read_bytes=physical_read, ddr_physical_write_bytes=physical_write,
                ddr_read_throttled_cycles=rstall, ddr_write_throttled_cycles=wstall,
                bandwidth_burst_allowance_bytes=128,
                read_port_ceiling_gbps=51.2,
                operation_cycles=dict(zip(op_names, (operations[i] for i in range(9)))),
                priority_bucket_cycles=dict(zip(reason_names, (reasons[i] for i in range(8)))),
                attribution_boundary='mutually exclusive priority buckets; overlapping causes are not additive and other includes active SFU work',
                scope='first layer first9 operators rows0_15 only; excludes attention and MLP')
r={'schema_version':1,'status':'PASS_CANONICAL_FIRST9_TILE16_PINNED_IDMA','evidence_class':'single_VCS_formal_descriptor_real_payload_clean_iDMA_AXI_bridge_SharedL2_fabric','commands':9,'rows':16,'descriptor_fetches':62,'abstract_dma_requests':145,'flat_idma_requests':101432,'axi_read_beats':104162,'axi_write_beats':104162,'completions':9,'bf16_bit_exact':118784,'matrix_steps':98304,'rope_steps':1920,'fragment_metrics':fragment_metrics(),'checks':{'dedicated_directional_chunk_gate':True,'max_DDR_to_local_flat_bytes':1024,'max_local_to_DDR_flat_bytes':64,'real_shared_l2_fabric':True,'real_AXI_to_L2_bridge':True,'upstream_idma_clean':True,'no_AXI_assertion_errors':True,'no_intermediate_reference_injection':True},'provenance':{'log_sha256':sha(LOG),'coalesce_log_sha256':sha(COAL),'top_rtl_sha256':sha('rtl/integration/qwen2_first9_tile16_controller.sv'),'expander_rtl_sha256':sha('rtl/integration/qwen2_tile_idma_expand.sv'),'bridge_rtl_sha256':sha('rtl/integration/qwen2_axi_shared_l2_bridge.sv'),'idma_wrapper_rtl_sha256':sha('rtl/integration/idma_backend_rw_axi_flat_wrap.sv'),'testbench_sha256':sha('tb/tb_qwen2_first9_tile16_pinned_idma_vcs.sv'),'idma_commit':'2e0b0fe53b6f8823319e2428e2e9abc2db149b7d'},'open':['feed_real_KV_append','q1024_weight_tile_outer_scheduler','remaining_layer0','seven_groups','P3'],'non_claims':['descriptor records are served by a formal-image responder rather than stored in the same real fabric instance','only canonical rows0..15 execute','does not close complete layer0']};(ROOT/'reports/execution/qwen2_first9_tile16_pinned_idma_result.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'bit_exact':118784,'flat':101432},sort_keys=True))
