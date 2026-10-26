"""Small synthetic text/files only. No native, subprocess, tool, or actual plan reads."""
import json
import pathlib
import tempfile
import types
import sys

HERE = pathlib.Path(__file__).parent
C = types.ModuleType('check_plan')
exec(compile((HERE/'check_plan.py').read_bytes(),str(HERE/'check_plan.py'),'exec'),C.__dict__)
P = 'VOrderedQkRealMatrixCorePlan'
O = C.ORIGINAL
N = O+'_a'
B = 'V'+N


def fixture(root):
    r = str(root)
    sources = ['/fixture/inputs/common.sv','/fixture/inputs/providers/wrapper.sv','/fixture/inputs/providers/impl.sv']
    cfg = ['/fixture/inputs/config/hierarchy.vlt','/fixture/inputs/config/raw.vlt']
    deps = sorted(sources+cfg+['/fixture/tool/bin/verilator_bin','/fixture/tool/include/verilated_std.sv','/fixture/tool/include/verilated_std_waiver.vlt'])
    args = ['--cc','--hierarchical','--make','cmake','-sv','--top-module',C.TOP,'--prefix',P,'--assert','--verilate-jobs','1','--threads','1','--no-timing','--Mdir',r]+cfg+sources
    m = {'prefix':P,'top':C.TOP,'original_module':O,'source_paths':sources,'config_paths':cfg,'dependency_paths':deps,'full_sv':sources[0],'backend':'/fixture/tool/bin/verilator_bin','verilator_root':'/fixture/tool','perl':'perl','python3':'python3','threads':1,'library_paths':[],'line_args':args}
    hier = O+','+N
    trailing = '"--make" "cmake" "-sv" "--assert" "--verilate-jobs" "1" "--no-timing" '+ ' '.join('"'+x+'"' for x in cfg)
    top = '--hierarchical-block '+hier+'\n--threads 1\n--cc\n"--cc" '+trailing+'\n'
    child = '--cc\n --prefix '+B+'\n --mod-prefix '+B+'\n --top-module '+N+'\n --lib-create '+N+'\n --hierarchical-child 1\n--hierarchical-block '+hier+'\n'+trailing+'\n'
    cm = '''# Verilated -*- CMake -*-
set(PERL "perl" CACHE FILEPATH "Perl executable (from $PERL, defaults to 'perl' if not set)")
set(PYTHON3 "python3" CACHE FILEPATH "Python3 executable (from $PYTHON3, defaults to 'python3' if not set)")
set(VERILATOR_ROOT "/fixture/tool" CACHE PATH "Path to Verilator kit (from $VERILATOR_ROOT)")
set(VERILATOR_SOLVER "z3 --in" CACHE STRING "Default SMT solver for constrained randomization (from $VERILATOR_SOLVER)")
'''
    for suffix,value in [('USER_CFLAGS',''),('USER_LDLIBS',''),('SC','0'),('COVERAGE','0'),('TIMING','0'),('THREADS','1'),('TRACE_VCD','0'),('TRACE_FST','0'),('GLOBAL','"${VERILATOR_ROOT}/include/verilated.cpp" "${VERILATOR_ROOT}/include/verilated_threads.cpp" '),('CLASSES_SLOW',''),('CLASSES_FAST',''),('SUPPORT_SLOW',''),('SUPPORT_FAST',''),('DEPS',''.join('"'+x+'" ' for x in deps)),('USER_CLASSES','')]:
        cm+='set('+P+'_'+suffix+' '+value+')\n'
    cm += 'get_target_property(TOP_TARGET_NAME "${TARGET}" NAME)\nadd_library('+B+' STATIC)\ntarget_link_libraries(${TOP_TARGET_NAME}  PRIVATE '+B+')\n'
    cm += 'verilate('+B+' PREFIX '+B+' TOP_MODULE '+N+' DIRECTORY '+r+'/'+B+' SOURCES  '+''.join(x+' ' for x in sources)+' VERILATOR_ARGS -f '+r+'/'+B+'__hierCMakeArgs.f -CFLAGS -fPIC)\n'
    cm += 'verilate(${TOP_TARGET_NAME} PREFIX '+P+' TOP_MODULE '+C.TOP+' DIRECTORY '+r+' SOURCES  '+r+'/'+B+'/'+N+'.sv '+''.join('"'+x+'" ' for x in sources)+' VERILATOR_ARGS -f '+r+'/'+P+'__hierCMakeArgs.f)\n'
    files = {P+'.cmake':cm,P+'__hierCMakeArgs.f':top,B+'__hierCMakeArgs.f':child}
    names = sorted(list(files)+[P+'__ver.d',P+'__verFiles.dat'])
    files[P+'__ver.d'] = ''.join(r+'/'+x+' ' for x in names if not x.endswith('__verFiles.dat'))+' : '+m['backend']+' '+''.join(x+' ' for x in deps)+'\n'
    dat='# DESCRIPTION: Verilator output: Timestamp data for --skip-identical.  Delete at will.\nC "synthetic not executable"\n'
    for path,role in sorted([(x,'S') for x in deps]+[(r+'/'+x,'T') for x in names]):
        dat+=role+'  0 0 1 1 1 1 "'+path+'"\n'
    files[P+'__verFiles.dat']=dat
    return m,files


def run():
    checks=0
    negatives=[]
    with tempfile.TemporaryDirectory(prefix='plan-tiny-') as tmp:
        root=pathlib.Path(tmp)/'plan';root.mkdir()
        m,base=fixture(root)
        def put(files):
            for p in root.iterdir():
                p.unlink()
            for n,text in files.items():
                (root/n).write_text(text)
        def reject(label,files=None,manifest=None):
            nonlocal checks
            put(files if files is not None else base)
            try:C.check_tree(str(root),manifest or m)
            except (ValueError,UnicodeError,KeyError):pass
            else:raise RuntimeError('accepted negative: '+label)
            checks+=1;negatives.append(label)
        put(base);res=C.check_tree(str(root),m)
        C.require(res['module_plan_count']==1 and not res['eight_state_instances_verified'] and res['overridden_parameter_count']==0, 'positive scope')
        checks+=1
        for name in base:
            fs=dict(base);del fs[name];reject('missing '+name,fs)
        for suffix in ['.cpp','.h','.o','.a','.so','.v','.sv','.mk','.elf']:
            fs=dict(base);fs['unknown'+suffix]='x\n';reject('extra '+suffix,fs)
        changes=[
            ('CMake unknown execute',P+'.cmake',lambda s:s+'execute_process(COMMAND bad)\n'),
            ('CMake extra variable',P+'.cmake',lambda s:s+'set(X bad)\n'),
            ('CMake wrong top',P+'.cmake',lambda s:s.replace('TOP_MODULE '+C.TOP,'TOP_MODULE Bad')),
            ('CMake wrong block',P+'.cmake',lambda s:s.replace('add_library('+B,'add_library(Bad')),
            ('CMake path injection',P+'.cmake',lambda s:s.replace('z3 --in','${EVIL}')),
            ('CMake solver semicolon',P+'.cmake',lambda s:s.replace('z3 --in','z3;bad')),
            ('CMake changed thread',P+'.cmake',lambda s:s.replace('_THREADS 1','_THREADS 2')),
            ('CMake unexpected cpp',P+'.cmake',lambda s:s.replace('_CLASSES_FAST )','_CLASSES_FAST "bad.cpp")')),
            ('CMake wrong dependency',P+'.cmake',lambda s:s.replace('/fixture/inputs/common.sv','/fixture/inputs/other.sv')),
            ('CMake no PIC',P+'.cmake',lambda s:s.replace('-CFLAGS -fPIC','')),
            ('top extra block',P+'__hierCMakeArgs.f',lambda s:s+'--hierarchical-block x,y\n'),
            ('top incorrect origin',P+'__hierCMakeArgs.f',lambda s:s.replace(O+',' ,'bad,')),
            ('top nonzero override',P+'__hierCMakeArgs.f',lambda s:s.replace(O+','+N,O+','+N+",ENABLE_ACCUMULATOR_SEED,1'h1")),
            ('top even zero override forbidden',P+'__hierCMakeArgs.f',lambda s:s.replace(O+','+N,O+','+N+",ENABLE_ACCUMULATOR_SEED,1'h0")),
            ('top wrong name family',P+'__hierCMakeArgs.f',lambda s:s.replace(N,'other_a')),
            ('top unhashed original forbidden',P+'__hierCMakeArgs.f',lambda s:s.replace(N,O)),
            ('top nonhex suffix',P+'__hierCMakeArgs.f',lambda s:s.replace(N,O+'_xyz')),
            ('top build injected',P+'__hierCMakeArgs.f',lambda s:s+'--build\n'),
            ('child -G injected',B+'__hierCMakeArgs.f',lambda s:s+"-GENABLE_ACCUMULATOR_SEED=1\\'h0\n"),
            ('child wrong count',B+'__hierCMakeArgs.f',lambda s:s.replace('child 1','child 2')),
            ('child source injected',B+'__hierCMakeArgs.f',lambda s:s+'/fixture/other.sv\n'),
            ('child type params',B+'__hierCMakeArgs.f',lambda s:s+'--hierarchical-params-file /fixture/bad.v\n'),
            ('MMD unknown dep',P+'__ver.d',lambda s:s.rstrip()+' /fixture/unpinned\n'),
            ('MMD omitted source',P+'__ver.d',lambda s:s.replace('/fixture/inputs/common.sv ','')),
            ('MMD added target',P+'__ver.d',lambda s:s.replace(' : ',' /tmp/other : ')),
            ('timestamp new source',P+'__verFiles.dat',lambda s:s+'S 0 0 0 0 0 0 "/fixture/unpinned"\n'),
            ('timestamp missing line',P+'__verFiles.dat',lambda s:'\n'.join(s.splitlines()[:-1])+'\n'),
            ('unbounded line',P+'.cmake',lambda s:s+'#'+('x'*65536)+'\n'),
            ('too many lines',P+'.cmake',lambda s:s+('#\n'*10000)),
            ('NUL',P+'.cmake',lambda s:s+'\0\n'),
            ('file cap',P+'.cmake',lambda s:'x'*(2*1024*1024+1)),
        ]
        for label,name,fn in changes:
            fs=dict(base);fs[name]=fn(fs[name]);reject(label,fs)
        for key,val in [('top','Wrong'),('threads',2),('library_paths',['/fixture/extra.sv']),('source_paths',m['source_paths']*2),('prefix','bad;evil')]:
            mm=dict(m);mm[key]=val;reject('manifest '+key,manifest=mm)
        put(base);p=root/(P+'.cmake');p.unlink();p.symlink_to('/dev/null')
        try:C.check_tree(str(root),m)
        except ValueError:pass
        else:raise RuntimeError('symlink accepted')
        checks+=1;negatives.append('symlink rejected')
        put(base)
        C.require(C.tokens('"--make" "cmake" abc 1\\\'h0') == ['--make','cmake','abc',"1'h0"], 'argument lexical positive')
        checks+=1
        C.require(C.forwarded(m['line_args'],m['source_paths'],False)[-2:]==m['config_paths'], 'config forwarding')
        checks+=1
    return {'status':'PASS_SOURCE_SYNTHETIC_ONLY','checks':checks,'negative_count':len(negatives),'negative_cases':negatives,'native_executed':False,'actual_plan_read':False,'optimized':not __debug__}

if __name__=='__main__':
    print(json.dumps(run(),indent=2))
