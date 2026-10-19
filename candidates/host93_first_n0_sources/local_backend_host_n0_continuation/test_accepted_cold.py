"""Synthetic-only checks for prior-qualification acceptance, never native probes."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('require -I -S -B')
import copy,json,tempfile,types
from pathlib import Path
from unittest import mock
checks=[]
def need(ok,why):
    if not ok:raise ValueError(why)
def rejects(fn,why):
    try:fn()
    except (ValueError,KeyError,TypeError,OSError):return
    raise ValueError('missing rejection: '+why)
def fixture():
    record={'exit_code':0,'status':'PASS','cleanup_confirmed':True,'timed_out':False,'reaped':True,'parent_exception':None,'exit_observed_while_unreaped':{'code':1,'status':0}}
    q={'status':'PASS_FIXED_FIVE_TOOL_VERSION_AND_GENERATION_ONLY','binding':{'synthetic':'binding'},'profile':{'synthetic':'profile'},'cpu_affinity_count':1,'shared_seconds_cap':480,'stage_result':{'synthetic':'stage69'},'records':[{'name':n,'record':copy.deepcopy(record)} for n in accepted.PHASES]}
    q.update({k:False for k in ('download_cleanup_inherited','backend_build_started','host_started','network_started')})
    q['qualification']={'versions':dict(accepted.VERSIONS),'version_count':5,'tiny_count':5,'generated_probe_code_executed':False,'probes':{t+'-'+m:{'exit_code':0,'cleanup_confirmed':True} for t in accepted.VERSIONS for m in ('version','micro')}}
    return q
base=fixture();g=types.SimpleNamespace(need=need)
need(accepted.validate(g,base,base['binding'],base['profile']) is base['qualification'],'positive existing qualification identity')
checks.append('synthetic_exact_existing_five_versions_ten_probes_thirteen_phase_control')
mutations=[]
for key,value in [('status','PASS'),('binding',{}),('profile',{}),('cpu_affinity_count',2),('shared_seconds_cap',6600)]+[(k,True) for k in ('download_cleanup_inherited','backend_build_started','host_started','network_started')]:
    mutations.append((key,lambda q,k=key,v=value:q.__setitem__(k,v)))
mutations.extend([('phase_missing',lambda q:q['records'].pop()),('phase_duplicate',lambda q:q['records'].__setitem__(1,copy.deepcopy(q['records'][0]))),('phase_reorder',lambda q:q['records'].reverse())])
for key,value in [('exit_code',True),('exit_code',1),('status','FAIL'),('cleanup_confirmed',False),('timed_out',True),('reaped',False),('parent_exception','failure')]:
    mutations.append(('phase_'+key+str(value),lambda q,k=key,v=value:q['records'][0]['record'].__setitem__(k,v)))
for key,value in [('code',2),('status',9)]:
    mutations.append(('wnowait_'+key,lambda q,k=key,v=value:q['records'][-1]['record']['exit_observed_while_unreaped'].__setitem__(k,v)))
for key,value in [('versions',{}),('version_count',4),('tiny_count',4),('generated_probe_code_executed',True)]:
    mutations.append(('qualification_'+key,lambda q,k=key,v=value:q['qualification'].__setitem__(k,v)))
mutations.extend([('probe_missing',lambda q:q['qualification']['probes'].pop('flex-micro')),('probe_extra',lambda q:q['qualification']['probes'].__setitem__('unknown',{})),('probe_unclean',lambda q:q['qualification']['probes']['flex-micro'].__setitem__('cleanup_confirmed',False)),('probe_bool_exit',lambda q:q['qualification']['probes']['m4-version'].__setitem__('exit_code',False))])
for name,change in mutations:
    q=fixture();change(q);rejects(lambda:accepted.validate(g,q,base['binding'],base['profile']),name);checks.append(name+'_rejected')
with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
    home=Path(tmp);repo=home/'repo';dep=home/'dependency';q=fixture();reads=[];identities=[];adapter_calls=[]
    c=make_ci();c.host_identities=lambda s:identities.append(s) or {};c.qualify_tools=mock.Mock(side_effect=AssertionError('qualification rerun forbidden'))
    qpath=home/'accepted.json';review=home/'review.json'
    def checked(path,pin,*args):
        path=Path(path);reads.append(path)
        if path==qpath:return json.dumps(q).encode()
        if path==review:return json.dumps({'all_natural_exit0_cleanup_true_no_timeout':True}).encode()
        if path==repo/adapter.CI:return CI_RAW
        raise ValueError('unexpected synthetic read '+str(path))
    def bind(*args):adapter_calls.append(args);return c,{'synthetic':'caller'}
    ag=types.SimpleNamespace(need=need,checked=checked,decode=json.loads,pin=pin,clean=lambda p:Path(p),binding=lambda *x:{'synthetic':'binding'},paths=lambda b:{'work':dep,'stage':dep/'stage'})
    ad=types.SimpleNamespace(bind=bind,CI=adapter.CI,CI_PIN=adapter.CI_PIN,exact_function=adapter.exact_function)
    hh=types.SimpleNamespace(bind=lambda *x:{'synthetic':'header'})
    component,proof=accepted.bind(ag,None,None,ad,hh,repo,b'{}',base['binding'],b'{}',base['profile'],qpath,review,b'synthetic-helper')
    need(len(adapter_calls)==1 and adapter_calls[0][-1]==q['stage_result'],'reuse exact existing stage')
    need(proof['run']['inverse_exact'] is True and proof['run']['substitutions']==3 and proof['new_tools_qualification_run'] is False,'finite inverse projection')
    for support in ('synthetic-support-1','synthetic-support-2'):
        out=component.accepted_tools(support)
        need(out['local_probe_rerun'] is False and out['qualification']==q['qualification'],'truthful existing receipt')
    need(identities==['synthetic-support-1','synthetic-support-2'] and c.qualify_tools.call_count==0,'live identities without ten reprobes')
    checks.append('accepted_bind_three_inverse_anchors_revalidates_each_use_without_probe_rerun')
    q['qualification']['tiny_count']=4
    rejects(lambda:component.accepted_tools('never'),'changed qualification before next identity')
    need(len(identities)==2,'tamper refused before further identities')
    checks.append('accepted_receipt_rechecked_before_each_use')
    for badrepo,work in ((repo,dep),(repo,dep/'nested'),(repo,home),(home/'wrong-repo',home/'new')):
        rejects(lambda:component.run(badrepo,work,mock.Mock(side_effect=AssertionError('callback forbidden'))),'root overlap or wrong repo')
    checks.append('overlapping_dependency_or_wrong_repo_refused_before_build')
print(json.dumps({'status':'PASS_ACCEPTED_TOOLCHAIN_SYNTHETIC_ONLY','tests':len(checks),'checks':checks,'optimized':sys.flags.optimize,'native_started':False,'network_started':False,'real_tools_copied':False},sort_keys=True))
TEST_RESULTS.append({'module':'test_accepted_cold.py','tests':len(checks),'checks':checks})
