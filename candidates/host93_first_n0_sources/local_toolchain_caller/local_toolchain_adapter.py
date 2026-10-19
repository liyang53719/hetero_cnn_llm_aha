"""Finite private-five-tool adapter for the original ci_toolchain caller.
No process/network API; the original caller's supervisor remains mandatory.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):raise SystemExit('require Python -I -S -B')
if __name__=='__main__':raise SystemExit('SOURCE module only')
import ast
import json
from pathlib import Path
import stat

CI='candidates/host93_ci_recovery/toolchain/ci_toolchain.py'
CI_PIN={'bytes': 46208, 'sha256': '5b0923a5f72dd9ecb34380aac176c86d5bf99010938cb6e6cb97a11299fe9a0a'}
BOOTSTRAP_PIN={'bytes':25509,'sha256':'c2a7ca58d8fba3df8b76071e25ad740386ab5113a59897181b39b4d303e50ea8'}
PROFILE_PIN={'bytes':7087,'sha256':'cdbe1030e3bf2a9b2222836f7f594b4800c4315dfb31a4438a8b76c07cd18c8f'}
OBSERVER_PIN={'bytes':11781,'sha256':'62a7f5b4f9250f66e5c62ed9d8b6a486642e135e5e934fc505ae2dfadc850904'}
PRIVATE_ENV=('PATH','AUTOM4TE','M4','LEX','YACC','autom4te_perllibdir','AC_MACRODIR','trailer_m4','AUTOM4TE_CFG','BISON_PKGDATADIR')


def exact_function(g,raw,name,ns,replacements=()):
    lines=raw.splitlines(keepends=True);nodes=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name==name]
    g.need(len(nodes)==1,'single fixed caller function')
    node=nodes[0];original=b''.join(lines[node.lineno-1:node.end_lineno])+b'\n';projected=original
    for old,new in replacements:
        g.need(projected.count(old)==1 and new not in projected,'single finite caller anchor');projected=projected.replace(old,new)
    recovered=projected
    for old,new in reversed(replacements):recovered=recovered.replace(new,old)
    g.need(recovered==original,'exact inverse caller projection')
    exec(compile(projected,'finite_local_'+name,'exec',dont_inherit=True),ns)
    return ns[name],{'original':g.pin(original),'projected':g.pin(projected),'substitutions':len(replacements),'inverse_exact':True}


def checked_inputs(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin):
    g.checked(Path(g.__file__),BOOTSTRAP_PIN)
    g.checked(Path(o.__file__),OBSERVER_PIN);g.checked(Path(l.__file__),PROFILE_PIN)
    b=g.binding(binding_raw,binding_pin,repo)
    g.need(type(profile_raw) is bytes and len(profile_raw)<=256*1024 and g.pin(profile_raw)==profile_pin,'same-buffer explicit local profile')
    profile=g.decode(profile_raw)
    g.need(profile['binding_pin']==binding_pin,'profile and binding same identity')
    l.validate(g,o,b,profile)
    return b,profile


def prepare(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin,stage_result):
    """Future separately authorized data-copy call; no native tool invocation."""
    b,profile=checked_inputs(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin)
    checker,proof=l.native_checker(g,o,b,profile)
    ns=dict(g.__dict__);ns['native_preflight']=checker
    raw=g.checked(Path(g.__file__),BOOTSTRAP_PIN)
    function,projected=exact_function(g,raw,'prepare_tools',ns)
    result=function(repo,binding_raw,binding_pin,stage_result)
    checked_inputs(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin)
    return result,{'native_preflight':proof,'prepare_tools':projected}


def private_map(g,b):
    root=g.paths(b)['tools']/'usr/bin'
    return {tool:str(root/tool) for tool in g.FIVE}


def bind(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin,stage_result):
    """Return a private original caller instance after all staged/copied checks.

    Returned run() retains its original native callback contract and budgets.
    Calling it is a separate actual action, not authorized by constructing this
    source adapter. There is no launch API or automatic copy/acquisition here.
    """
    repo=g.clean(repo);b,profile=checked_inputs(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin)
    s=g.load_sources(repo);p=g.paths(b);mapping=private_map(g,b)
    checker,native_proof=l.native_checker(g,o,b,profile)
    raw=g.checked(repo/CI,CI_PIN);component=g.module(raw,repo/CI,'fixed_local_ci_toolchain')
    original_environment=component.environment;original_commands=component.build_commands;original_phase=component.checked_phase
    def identities(support):
        checked_inputs(g,o,l,repo,binding_raw,binding_pin,profile_raw,profile_pin)
        expected=g.verify_stage(s,b,stage_result,binding_pin);checker(s,b,expected)
        tree=s['fs'].tree_inventory(p['tools'],8*g.MIB,68,256,4*g.MIB)
        regular={n:row for n,row in tree['entries'].items() if row['kind']=='regular'}
        g.need(set(regular)==set(expected),'exact private tool68 inventory')
        for name,pin in expected.items():
            mode='0o700' if name in {'usr/bin/'+tool for tool in g.FIVE} else '0o600'
            g.need({k:regular[name][k] for k in ('bytes','sha256','mode')}=={**pin,'mode':mode},'private tool bytes/mode drift')
            info=(p['tools']/name).lstat();g.need(info.st_nlink==1,'single-link private tool data')
        result=g.system_identities(s,b)
        for tool,invoked in mapping.items():
            row=regular['usr/bin/'+tool];result[invoked]={'path':invoked,**{k:row[k] for k in ('bytes','sha256','mode')}}
        g.need(set(result)==set(g.SYSTEM)|set(mapping.values()) and not set('/usr/bin/'+n for n in g.FIVE)&set(result),'truthful exact invocation keys')
        for name,pin in g.SOURCE_FILES.items():g.checked(repo/name,pin)
        g.checked(repo/CI,CI_PIN)
        return result
    def environment(work,verilator=None):
        result=original_environment(work,verilator);local=g.tool_environment(b)
        result.update({key:local[key] for key in PRIVATE_ENV})
        result['AUTOCONF']=mapping['autoconf']
        g.need(result['PATH'].split(':')[0]==str(p['tools']/'usr/bin'),'private path first')
        for key,tool in (('AUTOCONF','autoconf'),('AUTOM4TE','autom4te'),('M4','m4'),('LEX','flex'),('YACC','bison')):
            g.need(result[key]==mapping[tool],'explicit private tool environment')
        return result
    def commands(root,work,include):
        result=original_commands(root,work,include)
        g.need(result['autoconf'][0]=='/usr/bin/autoconf','fixed autoconf command anchor')
        result['autoconf'][0]=mapping['autoconf']
        for key,tool in (('LEX','flex'),('YACC','bison')):
            old=key+'=/usr/bin/'+tool;g.need(result['configure'].count(old)==1,'single configure tool anchor')
            result['configure'][result['configure'].index(old)]=key+'='+mapping[tool]
        g.need(result['make'].count('-j1')==1 and not any('-j' in x and x!='-j1' for x in result['make']),'unchanged single-core make')
        return result
    def phase(call_phase,support,tools,name,argv,cwd,env,bound,tree_root=None):
        forbidden={'/usr/bin/'+tool for tool in g.FIVE}
        g.need(type(argv) in (list,tuple) and argv and argv[0] not in forbidden and
               not any(x in ('LEX=/usr/bin/flex','YACC=/usr/bin/bison') for x in argv),'system five-tool fallback forbidden')
        home=g.clean(env['HOME']);verilator=Path(env['VERILATOR_ROOT']) if 'VERILATOR_ROOT' in env else None
        g.need(env==environment(home.parent,verilator),'exact private caller environment without fallback')
        return original_phase(call_phase,support,tools,name,argv,cwd,env,bound,tree_root)
    component.host_identities=identities;component.environment=environment;component.build_commands=commands;component.checked_phase=phase
    component.__dict__['LOCAL_TOOLS']=mapping
    _,probe_proof=exact_function(g,raw,'qualify_tools',component.__dict__,((b"['/usr/bin/' + tool]",b'[LOCAL_TOOLS[tool]]'),(b'onsite official-image tool identity and finite generation probes only',b'fixed official Debian package tools with bound local identities and finite generation probes only')))
    _,run_proof=exact_function(g,raw,'run',component.__dict__,((b"tools['/usr/bin/flex']",b"tools[LOCAL_TOOLS['flex']]"),))
    # Binding creates no output and checks all dependencies now, before run() can
    # create its separate fresh work root or call any supervisor callback.
    identities(s['fs'])
    original_run=component.run
    def run(repo_arg,work,call_phase,stop_after_build=False):
        target=g.clean(work)
        g.need(Path(repo_arg)==repo and not target.is_relative_to(p['work']) and not p['work'].is_relative_to(target),'separate fixed caller work root')
        return original_run(repo_arg,target,call_phase,stop_after_build)
    component.run=run
    return component,{'schema':'LOCAL_FIXED_TOOLCHAIN_CALLER_PROJECTION_V1','ci_source':CI_PIN,'native_preflight':native_proof,
                      'qualify_tools':probe_proof,'run':run_proof,'private_mapping':mapping,
                      'native_qualification':'NOT_RUN','actual_authorization':False,'original_resources_changed':False}
