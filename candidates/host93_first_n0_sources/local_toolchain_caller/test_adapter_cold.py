import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import ast,copy,json,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def check(n,fn):fn();checks.append(n)
def rejects(fn,text):
    try:fn()
    except (ValueError,OSError) as e:g.need(text in str(e),'wrong rejection '+str(e));return
    raise ValueError('missing rejection '+text)
# Reuse the already pinned published synthetic Fixture class, not package bytes.
name='candidates/host93_first_n0_sources/local_dependency_bootstrap/test_bootstrap_cold.py'
raw=g.checked(REPO/name,{'bytes':23019,'sha256':'40329861443bee643cf21eafefc822b36ddcd6e75a42885cae168abc70048477'})
node=[n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef) and n.name=='Fixture'][0]
lines=raw.splitlines(keepends=True);exec(compile(b''.join(lines[node.lineno-1:node.end_lineno])+b'\n','original_synthetic_fixture','exec'),globals())
class Ready:
    def __enter__(self):
        self.f=Fixture().__enter__();f=self.f;self.result=f.stage()
        self.validate=mock.patch.object(l,'validate',return_value=True);self.validate.start()
        self.native=mock.patch.object(l,'native_checker',return_value=(lambda *args:{'system_programs':{n:{'path':n,'synthetic':True} for n in g.SYSTEM},'status':'SYNTHETIC_STATIC'}, {'synthetic':True}));self.native.start()
        self.profile=o.canonical({'binding_pin':f.bpin});self.ppin=g.pin(self.profile)
        self.system=mock.patch.object(g,'system_identities',return_value={n:{'path':n,'synthetic':True} for n in g.SYSTEM});self.system.start()
        self.prepared,self.prepare_proof=a.prepare(g,o,l,REPO,f.braw,f.bpin,self.profile,self.ppin,self.result)
        self.c,self.proof=a.bind(g,o,l,REPO,f.braw,f.bpin,self.profile,self.ppin,self.result)
        return self
    def __exit__(self,*args):self.system.stop();self.native.stop();self.validate.stop();self.f.__exit__(*args)

def mapping():
 with Ready() as r:
    f=r.f;c=r.c;mp=a.private_map(g,f.b);tools=c.host_identities(f.s['fs'])
    g.need(set(tools)==set(g.SYSTEM)|set(mp.values()),'only truthful private keys')
    env=c.environment(Path('/synthetic/ci'),Path('/synthetic/verilator'))
    g.need(env['HOME']=='/synthetic/ci/home' and env['TMPDIR']=='/synthetic/ci/tmp','CI private home/tmp preserved')
    g.need(env['AUTOCONF']==mp['autoconf'] and env['LEX']==mp['flex'] and env['YACC']==mp['bison'],'private env')
    cmd=c.build_commands(Path('/synthetic/verilator'),Path('/synthetic/ci'),Path('/synthetic/header'))
    g.need(cmd['autoconf'][0]==mp['autoconf'] and 'LEX='+mp['flex'] in cmd['configure'] and 'YACC='+mp['bison'] in cmd['configure'],'fixed argv mapping')
    g.need(cmd['make'][3:5]==['-j1','opt'] and c.BUILD_LIMITS['make']['as_bytes']==4*g.GIB,'unchanged resources')
    g.need(r.proof['qualify_tools']['substitutions']==2 and r.proof['run']['substitutions']==1 and r.prepare_proof['prepare_tools']['substitutions']==0,'narrow inverse projections')
check('private_invocation_keys_env_commands_and_unchanged_resources',mapping)

def before_after():
 with Ready() as r:
    f=r.f;c=r.c;tools=c.host_identities(f.s['fs']);calls=[];env=c.environment(Path('/synthetic/ci'))
    def callback(*args):calls.append(args);return {'record':{'exit_code':0,'cleanup_confirmed':True},'raw_log':b'', 'usage':{}}
    c.checked_phase(callback,f.s['fs'],tools,'host_m4-version',[a.private_map(g,f.b)['m4'],'--version'],f.work,env,c.PROBE_LIMITS)
    g.need(len(calls)==1,'one original callback')
    (f.work/'tools/usr/bin/m4').write_bytes(b'drift')
    rejects(lambda:c.checked_phase(callback,f.s['fs'],tools,'host_m4-version',[a.private_map(g,f.b)['m4']],f.work,env,c.PROBE_LIMITS),'private tool bytes/mode drift')
    g.need(len(calls)==1,'drift rejects before callback without fallback')
 with Ready() as r:
    f=r.f;c=r.c;tools=c.host_identities(f.s['fs'])
    def callback(*args):
        (f.work/'tools/usr/bin/m4').write_bytes(b'drift');return {'record':{'exit_code':0,'cleanup_confirmed':True},'raw_log':b'', 'usage':{}}
    rejects(lambda:c.checked_phase(callback,f.s['fs'],tools,'host_m4-version',[a.private_map(g,f.b)['m4']],f.work,c.environment(f.work),c.PROBE_LIMITS),'private tool bytes/mode drift')
check('original_phase_guards_verify_before_and_after_without_fallback',before_after)

def input_refusal():
 with Ready() as r:
    f=r.f
    rejects(lambda:a.checked_inputs(g,o,l,REPO,f.braw,f.bpin,r.profile,{'bytes':len(r.profile),'sha256':'0'*64}),'same-buffer explicit local profile')
    wrong=o.canonical({'binding_pin':g.pin(b'other')});rejects(lambda:a.checked_inputs(g,o,l,REPO,f.braw,f.bpin,wrong,g.pin(wrong)),'profile and binding')
    rejects(lambda:r.c.run(REPO,f.work/'nested',lambda *a:None),'separate fixed caller work')
    rejects(lambda:r.c.run(REPO,REPO,lambda *a:None),'fresh private output')
check('wrong_profile_buffer_binding_and_overlapping_run_root_rejected',input_refusal)

def projection_refusal():
 raw=g.checked(REPO/a.CI,a.CI_PIN);ns={}
 rejects(lambda:a.exact_function(g,raw,'run',ns,((b'absent anchor',b'replacement'),)),'single finite caller anchor')
check('unknown_projection_anchor_refuses',projection_refusal)
def fallback_refusal():
 with Ready() as r:
    f=r.f;c=r.c;tools=c.host_identities(f.s['fs']);env=c.environment(f.work);callback=mock.Mock(side_effect=AssertionError('forbidden fallback reached callback'))
    for name in g.FIVE:
        rejects(lambda:c.checked_phase(callback,f.s['fs'],tools,'host_'+name,['/usr/bin/'+name],f.work,env,c.PROBE_LIMITS),'system five-tool fallback')
    for key,value in (('M4','/usr/bin/m4'),('LEX','/usr/bin/flex'),('PATH','/usr/bin:/bin'),('LD_LIBRARY_PATH','/tmp/untrusted')):
        bad=dict(env);bad[key]=value
        rejects(lambda:c.checked_phase(callback,f.s['fs'],tools,'host_m4',[a.private_map(g,f.b)['m4']],f.work,bad,c.PROBE_LIMITS),'exact private caller environment')
    g.need(callback.call_count==0,'no fallback callback')
check('all_five_system_aliases_and_env_fallback_rejected_before_callback',fallback_refusal)

def ten_probes():
 with Ready() as r:
    f=r.f;c=r.c;support,pins,buffers=c.load_sources(REPO);modes=json.loads(buffers[c.MODES])['modes'];calls=[];mapping=a.private_map(g,f.b)
    def callback(name,argv,cwd,env,limits):
        mode=modes[name.removeprefix('host_')];tool=mode['tool'];g.need(argv==[mapping[tool]]+mode['argv_tail'],'every original probe uses actual private tool')
        for filename,output in mode['generated_files'].items():c.write_fixture(cwd/filename,('\n'.join(output['contains'])+'\n').encode())
        raw=(mode['expected_log_contains'][0]+'\n').encode() if name.endswith('-version') else mode['expected_log_exact'].encode()
        calls.append(name);return {'record':{'exit_code':0,'cleanup_confirmed':True},'raw_log':raw,'usage':{}}
    result=c.qualify_tools(support,c.host_identities(support),buffers,f.work,callback,c.environment(f.work))
    g.need(len(calls)==10 and result['version_count']==result['tiny_count']==5,'all ten original qualifications')
    g.need(result['scope']=='fixed official Debian package tools with bound local identities and finite generation probes only','truthful package source scope')
check('all_ten_original_version_generation_probes_use_private_argv_and_scope',ten_probes)

def false_tool_keys():
 with Ready() as r:
    f=r.f;c=r.c;valid=c.host_identities(f.s['fs']);key=a.private_map(g,f.b)['flex'];callback=mock.Mock(side_effect=AssertionError('bad key reached callback'))
    for kind in ('missing','system_alias','swapped'):
        changed=copy.deepcopy(valid);row=changed.pop(key)
        if kind=='system_alias':changed['/usr/bin/flex']=row
        elif kind=='swapped':changed[a.private_map(g,f.b)['m4']]=row
        rejects(lambda:c.checked_phase(callback,f.s['fs'],changed,'host_flex',[key],f.work,c.environment(f.work),c.PROBE_LIMITS),'in-job tool identity')
    g.need(callback.call_count==0,'missing/replaced/private keys before callback')
check('deleted_swapped_and_system_impostor_private_keys_fail_before_callback',false_tool_keys)

print(json.dumps({'status':'PASS_FINITE_LOCAL_CALLER_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'real_tools_copied':False},sort_keys=True))
