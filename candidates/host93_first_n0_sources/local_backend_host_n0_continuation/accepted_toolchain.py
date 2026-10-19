"""Consume exact previously reviewed local five-tool evidence, then fresh build/tiny."""
import sys
if not(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require -I -S -B')
import json
from pathlib import Path
QUALIFICATION_PIN={'bytes':75078,'sha256':'c4f9e7242b3762b72055c4a87f388286c2b84df0aea3a462b4f637e1004d4cd9'}
REVIEW_PIN={'bytes':3567,'sha256':'8cc44a685098d90074096609df24cee51974d690de43a27db3ea216b873837b2'}
VERSIONS={'autoconf':'2.72','autom4te':'2.72','m4':'1.4.19','flex':'2.6.4','bison':'3.8.2'}
PHASES=('local_dependencies_accept_cached','local_dependencies_stage_preset','local_dependencies_prepare_private')+tuple('host_'+t+'-'+mode for mode in ('version','micro') for t in VERSIONS)
def validate(g,q,bpin,ppin):
    g.need(q['status']=='PASS_FIXED_FIVE_TOOL_VERSION_AND_GENERATION_ONLY' and q['binding']==bpin and q['profile']==ppin,'exact prior qualification binding')
    for key in ('download_cleanup_inherited','backend_build_started','host_started','network_started'):g.need(q[key] is False,'qualification exact finite scope')
    g.need(q['cpu_affinity_count']==1 and q['shared_seconds_cap']==480,'qualification original resource scope')
    g.need([r['name'] for r in q['records']]==list(PHASES),'exact prior thirteen phases')
    for row in q['records']:
        r=row['record'];g.need(type(r['exit_code']) is int and r['exit_code']==0 and r['status']=='PASS' and r['cleanup_confirmed'] is True and r['timed_out'] is False and r['reaped'] is True and r['parent_exception'] is None,'natural clean prior phase')
        w=r['exit_observed_while_unreaped'];g.need(w['code']==1 and w['status']==0,'natural prior WNOWAIT exit')
    v=q['qualification'];g.need(v['versions']==VERSIONS and v['version_count']==v['tiny_count']==5 and v['generated_probe_code_executed'] is False,'five exact qualified versions and micros')
    g.need(set(v['probes'])=={t+'-'+m for t in VERSIONS for m in ('version','micro')},'exact ten prior probes')
    for r in v['probes'].values():g.need(type(r['exit_code']) is int and r['exit_code']==0 and r['cleanup_confirmed'] is True,'prior probe qualified')
    return v

def bind(g,o,l,adapter,header,repo,braw,bpin,praw,ppin,qualification_path,review_path,header_raw):
    raw=g.checked(Path(qualification_path),QUALIFICATION_PIN,256*1024);q=g.decode(raw);v=validate(g,q,bpin,ppin)
    review=g.decode(g.checked(Path(review_path),REVIEW_PIN,65536))
    g.need(review['all_natural_exit0_cleanup_true_no_timeout'] is True,'fixed reviewed qualification accepted')
    component,caller_proof=adapter.bind(g,o,l,repo,braw,bpin,praw,ppin,q['stage_result'])
    binding=g.binding(braw,bpin,repo);source=g.paths(binding)['stage']/'usr/include/FlexLexer.h'
    header_proof=header.bind(g,adapter,component,source,header_raw)
    def accepted(*args):
        current=g.decode(g.checked(Path(qualification_path),QUALIFICATION_PIN,256*1024));validate(g,current,bpin,ppin)
        g.checked(Path(review_path),REVIEW_PIN,65536)
        component.host_identities(args[0])
        return {'status':'ACCEPTED_EXISTING_LOCAL_FIVE_TOOL_QUALIFICATION','actual_result_pin':QUALIFICATION_PIN,'actual_review_pin':REVIEW_PIN,'local_probe_rerun':False,'qualification':v}
    component.__dict__['accepted_tools']=accepted
    original=g.checked(repo/adapter.CI,adapter.CI_PIN)
    _,proof=adapter.exact_function(g,original,'run',component.__dict__,((b"tools['/usr/bin/flex']",b"tools[LOCAL_TOOLS['flex']]"),(b'qualification = qualify_tools(support, tools, buffers, work, call_phase, env)',b'qualification = accepted_tools(support, tools, buffers, work, call_phase, env)'),(b"'historical_actual_or_review_inherited': False",b"'existing_local_tool_qualification_reused': True")))
    original_run=component.run
    def run(repo_arg,work,call_phase,stop_after_build=False):
        target=g.clean(work);dep=g.paths(binding)['work']
        g.need(Path(repo_arg)==repo and not target.is_relative_to(dep) and not dep.is_relative_to(target),'separate fresh build root')
        return original_run(repo_arg,target,call_phase,stop_after_build)
    component.run=run
    return component,{'caller':caller_proof,'header':header_proof,'run':proof,'prior_qualification':QUALIFICATION_PIN,'prior_review':REVIEW_PIN,'new_tools_qualification_run':False}
