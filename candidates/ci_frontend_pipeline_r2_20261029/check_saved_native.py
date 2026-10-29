"""Read-only grammar regression over caller-selected saved native frontend output.
Prerequisite pins derived here are TEST FIXTURE pins, not production provenance.
Production receives the independently reviewed source/tool/actual frontend closure.
"""
import argparse,json,tempfile,pathlib
from native_dependency_guard import admit_native_dependencies,digest
p=argparse.ArgumentParser();p.add_argument('--obj',type=pathlib.Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--child',action='append',default=[]);a=p.parse_args();obj=a.obj.resolve();known={};files=list(obj.rglob('*.d'))
for f in files:
 for q in f.read_text().split(' : ')[1].split():
  x=pathlib.Path(q);known[str(x)]=digest(x)
with tempfile.TemporaryDirectory()as d:
 generated,deps,rows=admit_native_dependencies(obj,{a.prefix:obj,**{n:obj/n for n in a.child}},known,d)
 print(json.dumps({'scope':'SAVED_NATIVE_GRAMMAR_TEST_ONLY_NOT_INDEPENDENT_PROVENANCE','files':rows,'derived_count':len(generated),'fixture_prerequisite_count':len(known)},indent=2))
