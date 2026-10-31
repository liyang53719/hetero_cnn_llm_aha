"""Synthetic scanner workload only; no real hardware, EDA, or baseline acceptance."""
import hashlib,json,pathlib,sys,tempfile,time,resource
D=pathlib.Path(__file__).resolve().parent;M=D.parent/'ci_frontend_materialization_r2_20261029';sys.path.insert(0,str(M));sys.path.insert(0,str(D))
import sv_comment_only_identity as scanner
from module_fingerprints import fingerprints
from sv_inventory_single_pass import inventory
assert hashlib.sha256((M/'sv_comment_only_identity.py').read_bytes()).hexdigest()=='b49c75780d2bfb295d3e90df6d478475f42c3129dba73c850b4d564e4114965b'
with tempfile.TemporaryDirectory(dir=pathlib.Path.cwd())as td:
 p=pathlib.Path(td)/'synthetic.sv';line=b'  assign wire_signal = input_signal; // @[/synthetic/source/Representative.scala 123:45]\n';unit=line*4096
 with p.open('wb')as f:
  for i in range(96):f.write(b'module Bench'+str(i).encode()+b'(\n);\n'+unit+b'endmodule\n')
 before=time.monotonic();counts={}
 with p.open('rb')as f:h=scanner.digest(f,counts)
 whole_seconds=time.monotonic()-before;start=time.monotonic()
 old_modules=fingerprints(p);modules_seconds=time.monotonic()-start
 with p.open('rb')as f:raw=hashlib.file_digest(f,'sha256').hexdigest()
 old=dict(raw_sha256=raw,normalized_sha256=h,bytes=p.stat().st_size,counts=counts,modules=old_modules)
 start=time.monotonic();new=inventory(p,scanner);new_seconds=time.monotonic()-start
 if new!=old:raise ValueError('synthetic exact full and module metadata differential failed')
 print(json.dumps(dict(schema='SYNTHETIC_SV_SCANNER_DIFFERENTIAL_BENCHMARK_V1',scope='SYNTHETIC_ONLY_NOT_ACTUAL_SV_ACCEPTANCE',input_bytes=p.stat().st_size,modules=96,baseline_whole_scan_seconds=whole_seconds,baseline_modules_scan_seconds=modules_seconds,single_pass_inventory_seconds=new_seconds,all_metadata_exact_equal=True,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,scanner_sha256=hashlib.sha256((M/'sv_comment_only_identity.py').read_bytes()).hexdigest(),inventory_source_sha256=hashlib.sha256((D/'sv_inventory_single_pass.py').read_bytes()).hexdigest(),numerical_pass=False)))
