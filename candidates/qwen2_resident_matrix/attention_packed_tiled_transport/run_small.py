"""Explicit one-job cases; invocation requires separately reviewed supervision."""
import argparse,hashlib,json,platform,resource,signal,sys,time
from pathlib import Path
from . import prepare
from .fixture import actual_case,LIB_SHA

def run(library,rows):
 if type(rows) is not int or rows not in (17,32):raise ValueError('bounded M17/M32 only')
 before=prepare.verify_installed();lib=Path(library)
 if hashlib.sha256(lib.read_bytes()).hexdigest()!=LIB_SHA:raise ValueError('qualified library')
 started=time.monotonic();cpu=time.process_time()
 cases=[actual_case(str(lib),rows,stalls=True)]
 if rows==17:cases += [actual_case(str(lib),17,stalls=True,fault=f) for f in ('panel_abort','panel_ddr_error')]
 if prepare.verify_installed()!=before or hashlib.sha256(lib.read_bytes()).hexdigest()!=LIB_SHA:raise ValueError('postflight drift')
 return dict(status='PASS_BOUNDED_TILED_PUBLIC_TRANSPORT',rows=rows,cases=cases,source_sha256=before,library_sha256=LIB_SHA,
  wall_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
  interpreter_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),python_version=platform.python_version(),
  new_compilation=False,one_job_per_case=True,full_public_graph=False,rtl=False,hardware_cycles=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--library',required=True);p.add_argument('--rows',type=int,choices=(17,32),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('fresh receipt only')
 start=time.monotonic();before=None
 def timeout(*args):raise TimeoutError('90-second fixture deadline')
 old=signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,90)
 try:
  before=prepare.verify_installed();report=run(a.library,a.rows)
 except BaseException as e:
  report=dict(status='FAILED_TILED_PUBLIC_TRANSPORT',rows=a.rows,error_type=type(e).__name__ if type(e).__name__ in ('ValueError','AssertionError','TimeoutError','ArithmeticError','MatrixProtocolError') else 'Other',source_sha256=before,postflight_complete=False,wall_seconds=time.monotonic()-start,full_public_graph=False,rtl=False)
  a.output.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n');raise
 else:a.output.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
if __name__=='__main__':main()
