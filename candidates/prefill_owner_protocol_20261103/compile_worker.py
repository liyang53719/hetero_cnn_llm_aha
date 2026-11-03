"""Serial compile/link of exact generated sources; never translate or execute ELF."""
import json,pathlib,re,subprocess,sys
P=pathlib.Path
obj,inc,driver,cxx,out=map(P,sys.argv[1:]);out.mkdir(exist_ok=False)
text=(obj/'VTransposedDenseDownOwner_classes.mk').read_text();groups={}
for name in ['VM_CLASSES_FAST','VM_CLASSES_SLOW','VM_SUPPORT_FAST','VM_SUPPORT_SLOW','VM_GLOBAL_FAST','VM_GLOBAL_SLOW']:
 m=re.search(r'^'+name+r'\s*\+=\s*\\\n((?:[ \t]+[^\n]+\n)*)',text,re.M);assert m,name
 groups[name]=re.findall(r'^\s+(\w+)\s*\\',m[1],re.M)
rows=[]
for kind in groups:
 for name in groups[kind]:rows.append((inc if 'GLOBAL'in kind else obj,name,'-O0'if kind.endswith('SLOW')else'-O1'))
assert len(rows)==51 and len(set(x[1]for x in rows))==51
rows.insert(0,(driver.parent,driver.stem,'-O1'));assert len(rows)==52
flags=['-I'+str(obj),'-I'+str(inc),'-I'+str(inc/'vltstd'),'-I'+str(driver.parent),'-DVM_COVERAGE=0','-DVM_SC=0','-DVM_TIMING=0','-DVM_TRACE=0','-DVM_TRACE_FST=0','-DVM_TRACE_VCD=0','-faligned-new','-fcf-protection=none','-Wno-bool-operation','-Wno-shadow','-Wno-sign-compare','-Wno-tautological-compare','-Wno-uninitialized','-Wno-unused-but-set-parameter','-Wno-unused-but-set-variable','-Wno-unused-parameter','-Wno-unused-variable','-std=c++17','-fno-fast-math','-ffp-contract=off','-MD','--param=ggc-min-expand=10','--param=ggc-min-heapsize=4096']
recipes=[]
for root,name,opt in rows:
 source=root/(name+'.cpp');assert source.is_file()
 argv=[str(cxx),opt,*flags,'-MF',str(out/(name+'.d')),'-c','-o',str(out/(name+'.o')),str(source)]
 print('COMPILE',json.dumps(argv),flush=True);subprocess.run(argv,check=True,timeout=300);recipes.append({'source':str(source),'object':name+'.o','argv':argv})
argv=[str(cxx),*(str(out/(r['object']))for r in recipes),'-pthread','-lpthread','-latomic','-o',str(out/'owner_protocol')]
print('LINK',json.dumps(argv),flush=True);subprocess.run(argv,check=True,timeout=120)
(out/'RECIPES.json').write_text(json.dumps({'compile':recipes,'link':argv,'model_executed':False},indent=2)+'\n')
