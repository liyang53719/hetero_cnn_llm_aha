import pathlib,json,hashlib,subprocess,os,time,resource,sys
r=pathlib.Path(__file__).resolve().parent;phase=sys.argv[1];used=json.loads((r.parent/'chunk_chisel_resume_2134/results/ACTUAL_DEPENDENCIES.json').read_text())['used']
for p in used:assert hashlib.sha256(pathlib.Path(p['path']).read_bytes()).hexdigest()==p['sha256']
(r/'build').mkdir(exist_ok=True);(r/'results').mkdir(exist_ok=True)
cp=os.pathsep.join(p['path'] for p in used);plugin=next(p['path'] for p in used if p['name'].startswith('chisel-plugin'))
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx1200m']
if phase=='compile':
 subprocess.run([sys.executable,str(r/'generate_fixture.py')],check=True)
 cmd=java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(r/'build')]+[str(f) for f in sorted((r/'upstream').glob('*.scala'))]+[str(r/'Fixture.scala'),str(r/'LoadPrepCheck.scala')]
else:cmd=java+['-cp',str(r/'build')+os.pathsep+cp,'LoadPrepCheck',phase]
t=time.monotonic();start=resource.getrusage(resource.RUSAGE_CHILDREN)
def limit():resource.setrlimit(resource.RLIMIT_CPU,(120,125))
with (r/'results'/f'{phase}.log').open('w') as f:
 try:code=subprocess.run(cmd,cwd=r,stdout=f,stderr=subprocess.STDOUT,timeout=150,preexec_fn=limit).returncode
 except subprocess.TimeoutExpired:code='WALL_TIMEOUT'
end=resource.getrusage(resource.RUSAGE_CHILDREN)
res={'phase':phase,'exit':code,'wall_seconds':time.monotonic()-t,'cpu_seconds':end.ru_utime+end.ru_stime-start.ru_utime-start.ru_stime,'max_rss_kib':end.ru_maxrss}
(r/'results'/f'{phase}.json').write_text(json.dumps(res,indent=2)+'\n');print(res,flush=True)
