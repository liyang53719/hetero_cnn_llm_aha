import pathlib,json,hashlib,subprocess,time,os,resource
R=pathlib.Path(__file__).resolve().parent;W=R.parents[2];src=W/'round_20261110T0133/current_original_source'
j=json.loads((W/'round_20261110T0633/gradual_head4/results/DEPENDENCY_RESOLUTION.json').read_text())['used']
for x in j:
 if hashlib.sha256(pathlib.Path(x['path']).read_bytes()).hexdigest()!=x['sha256']:raise ValueError(x['name'])
cp=os.pathsep.join(x['path'] for x in j);plugin=next(x['path'] for x in j if x['name'].startswith('chisel-plugin_'))
(R/'classes').mkdir(exist_ok=True)
b=W/'round_20261110T0133/recovery/sources/hetero_cloud_recovery_20261107T2134'
rows=json.loads((b/'candidates/chisel_hybrid_host_20261106/SOURCES.json').read_text())['sources']
files=[]
for x in rows:
 if x['phase']=='original162':
  p=b/x['path']
  if hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:raise ValueError('source pin '+x['path'])
  files.append(p)
files+=[R/'EmitV4Interface.scala']
(R/'SOURCE_HASHES.json').write_text(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},indent=2))
java=['java','-XX:-UsePerfData','-XX:ActiveProcessorCount=1','-Xmx3000m']
commands=[('compile',java+['-cp',cp,'scala.tools.nsc.Main','-classpath',cp,'-Xplugin:'+plugin,'-d',str(R/'classes')]+list(map(str,files))),('emit',java+['-cp',str(R/'classes')+':'+cp,'EmitV4Interface',str(R/'HostBlockTopV4.fir')])]
(R/'COMMANDS.json').write_text(json.dumps(commands,indent=2))
for name,cmd in commands:
 t=time.monotonic()
 with (R/(name+'.log')).open('w') as log:
  p=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True)
  (R/(name+'_identity.json')).write_text(json.dumps(dict(pid=p.pid,boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),starttime=pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text().split()[21])))
  try:rc=p.wait(timeout=240)
  except subprocess.TimeoutExpired:os.killpg(p.pid,9);p.wait();rc='TIMEOUT'
 result=dict(stage=name,exit=rc,seconds=time.monotonic()-t,scope='SOURCE_COMPILE_OR_IR_ONLY_NO_SIMULATION');(R/(name+'.json')).write_text(json.dumps(result,indent=2));print(result,flush=True)
 if rc!=0:break
