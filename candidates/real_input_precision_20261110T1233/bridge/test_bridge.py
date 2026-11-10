import json,tempfile,subprocess
from pathlib import Path
from adapt import adapt,ROOT
HERE=Path(__file__).resolve().parent
p=ROOT/'round_20261110T0733/qwen2_host_payload'
with tempfile.TemporaryDirectory(dir=HERE) as tmp:
 t=Path(tmp);r=adapt(p,t/'payload',HERE/'rope.f32le')
 subprocess.run([str(HERE/'config_probe'),str(t/'payload/host.tsv')],check=True)
 lines=(t/'payload/views.tsv').read_text().splitlines()[1:];names={x.split('\t')[1] for x in lines}
 assert names=={'commands','descriptors','rope','wq','wk','wv','wo','wg','wu','wd','gamma0','gamma1','bq','bk','bv','x'}
 alloc=(t/'payload/host.tsv').read_text(); assert 'allocation\tcache_k\t' not in alloc and 'allocation\tcache_v\t' not in alloc
 assert '\tvirtual\n' in alloc and 'scores' not in names and 'probabilities' not in names
 bad=t/'bad.f32le';bad.write_bytes(bytes(524288))
 try:adapt(p,t/'must_not_exist',bad)
 except AssertionError:pass
 else:raise AssertionError('zero RoPE admitted')
 assert not (t/'must_not_exist').exists()
 # Bad source digest rejected by original mmap loader, not only Python adapter.
 v=t/'payload/views.tsv';v.write_text(v.read_text().replace(lines[0].split('\t')[-1],'0'*64,1))
 x=subprocess.run([str(HERE/'config_probe'),str(t/'payload/host.tsv')],capture_output=True,text=True);assert x.returncode!=0 and 'SHA256 mismatch' in x.stderr
 print(json.dumps(dict(status='PASS_FORMAT_SMALL_TESTS_ONLY',positive_original_config=True,negative_zero_rope=True,negative_source_sha=True,virtual_not_preloaded=True,kv_alias_not_double_allocated=True,host_executed=False)))
