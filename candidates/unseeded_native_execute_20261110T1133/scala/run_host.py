from pathlib import Path
import subprocess,json,time,os
r=Path('round_20261110T1133/scala').resolve();out=r/'host_run';out.mkdir(exist_ok=True)
cmd=['java','-Xmx4g','-XX:ActiveProcessorCount=1','-cp',(r/'HOST_CLASSPATH.txt').read_text(),'chiseltest.simulator.RunCurrentHost',str(Path('round_20261110T0733/qwen2_execution/v4_legacy_pipeline/HostBlockTopV4.fir').resolve())]+[str(Path('round_20261110T1133/native',f).resolve()) for f in ['libmatrix_unseeded_v2.so','libicg.so','libidma.so']]+[str(out.relative_to(Path.cwd()))]
(r/'HOST_COMMAND.json').write_text(json.dumps(cmd));t=time.monotonic()
if (r/'HOST_RESULT.json').exists():(r/'HOST_RESULT.json').rename(r/('HOST_RESULT.previous.'+str(time.time_ns())+'.json'))
(r/'ACTIVE.json').write_text(json.dumps({'status':'STARTING','scope':'current originalHost construction, not prefill'}))
with (r/'host_run.log').open('w') as f:
 p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 (r/'HOST_IDENTITY.json').write_text(json.dumps({'pid':p.pid,'pgid':p.pid,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'starttime':Path(f'/proc/{p.pid}/stat').read_text().split()[21]},indent=2))
 try:code=p.wait(timeout=600);timeout=False
 except subprocess.TimeoutExpired:
  import signal
  os.killpg(p.pid,signal.SIGKILL);code=p.wait();timeout=True
(r/'HOST_RESULT.json').write_text(json.dumps({'exit':code,'timeout':timeout,'seconds':time.monotonic()-t,'scope':'original Chisel Host + actual native RTL leaves; construction/reset only not fullprefill'},indent=2));(r/'ACTIVE.json').write_text(json.dumps({'status':'TERMINAL','exit':code,'timeout':timeout}));print(code)
