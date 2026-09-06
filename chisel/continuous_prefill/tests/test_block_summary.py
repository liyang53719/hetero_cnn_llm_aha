"""The final report must reject mismatched geometry, work and stage coverage."""
from pathlib import Path
import json,subprocess,sys
import pytest
SCRIPT=Path(__file__).resolve().parents[1]/'scripts/summarize_block_gate.py'
def make(tmp_path,retained=False):
    (tmp_path/'generated').mkdir();(tmp_path/'source_commit.txt').write_text('a'*40)
    lo=dict(hidden=64,ffn=128,heads=2,kv_heads=1,head_dim=32,retained_matrix=retained)
    (tmp_path/'generated/layout.json').write_text(json.dumps(lo))
    text='\n'.join(f'STAGE_CHECK phase={i}' for i in range(15))+'\n'
    text+='CONTINUOUS_QWEN2_BLOCK_PASS tokens=2 hidden=64 ffn=128 heads=2 kv_heads=1 phases=15 checked_fp32=2112 bit_diffs=0 max_abs=0 cycles=92215 macs=74112 read_bytes=309760 write_bytes=8448 request_stalls=1 response_delay_cycles=1 hash=abc host_intermediate_writes=0 full_model=0 canonical_512_array='+str(int(retained))+' executed_macs='+str(74112*(32 if retained else 1))+'\n'
    p=tmp_path/'tokens_2.log';p.write_text(text);return p
@pytest.mark.parametrize('retained',[False,True])
def test_valid_summary(tmp_path,retained):
    make(tmp_path,retained);r=subprocess.run([sys.executable,str(SCRIPT),str(tmp_path)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)['canonical_matrix_512_integration']==retained
@pytest.mark.parametrize('a,b',[('phase=14','phase=0'),('checked_fp32=2112','checked_fp32=1'),('macs=74112','macs=1'),('hidden=64','hidden=32'),('executed_macs=74112','executed_macs=1')])
def test_corrupt_summary(tmp_path,a,b):
    p=make(tmp_path);p.write_text(p.read_text().replace(a,b))
    for optimize in [False,True]:
        cmd=[sys.executable]+(['-O'] if optimize else [])+[str(SCRIPT),str(tmp_path)]
        assert subprocess.run(cmd,capture_output=True).returncode!=0
