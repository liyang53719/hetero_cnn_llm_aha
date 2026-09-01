#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
pat=r'physical_columns=1536 column_tiles=48 descriptor_fetches=12 abstract_dma=98 flat_idma=73778 axi_beats=73920 ddr_read_bytes=4727808 ddr_write_bytes=3072 l2_read_beats=73872 l2_write_beats=96 rms_executions=1 matrix_completion=1 bf16_bit_exact=3072 pingpong_buffers=2 device_cycles=(\d+) overlap_cycles=(\d+)'
slog='work/results/qwen2_full_q_token_single_command/tb.log';plog='work/results/qwen2_full_q_token_pingpong/tb.log';sm=re.search(r'QWEN2_FULL_Q_TOKEN_SINGLE_COMMAND_PASS '+pat,(ROOT/slog).read_text());pm=re.search(r'QWEN2_FULL_Q_TOKEN_PINGPONG_PASS '+pat,(ROOT/plog).read_text())
if not sm or not pm:raise SystemExit('serial/pingpong receipts missing')
serial,serial_overlap=map(int,sm.groups());parallel,overlap=map(int,pm.groups());ratio=parallel/serial
checks={'same_outputs_and_traffic':True,'ratio_lte_0p65':ratio<=0.65,'real_overlap':overlap>0,'pingpong_buffers_2':True,'one_RMS_and_completion':True}
if not all(checks.values()):raise SystemExit(str(checks))
r={'schema_version':1,'status':'PASS_FULL_Q_TOKEN0_PINGPONG_OVERLAP','evidence_class':'single_VCS_real_pinned_idma_and_Matrix_concurrent','serial_cycles':serial,'pingpong_cycles':parallel,'overlap_cycles':overlap,'overlapped_over_serialized_ratio':ratio,'cycle_reduction':serial-parallel,'cycle_reduction_fraction':1-ratio,'physical_Q_columns':1536,'column_tiles':48,'bf16_bit_exact':3072,'ddr_read_bytes':4727808,'ddr_write_bytes':3072,'checks':checks,'provenance':{'serial_log_sha256':sha(slog),'pingpong_log_sha256':sha(plog),'pingpong_top_sha256':sha('rtl/integration/qwen2_full_q_pingpong_top.sv')},'non_claims':['token0 exercises one Matrix output row and does not prove q1024 Matrix utilization >=85%','full q1024 payload, QKV, complete layer, P2 and P3 remain open']};out=ROOT/'reports/execution/qwen2_full_q_token_pingpong_result.json';out.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':r['status'],'serial':serial,'pingpong':parallel,'ratio':ratio},sort_keys=True))
