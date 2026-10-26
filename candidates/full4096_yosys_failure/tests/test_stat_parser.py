from pathlib import Path
import json,copy,types,tempfile
R=Path(__file__).resolve().parents[1]
s=types.ModuleType("stat_parser");s.__file__=str(R/"source/stat_parser.py")
exec(compile((R/"source/stat_parser.py").read_bytes(),s.__file__,"exec"),s.__dict__)
m={"top":"OrderedQkRealMatrixCore","caps":{"single_file_hard_bytes":192*1024**2,"log_hard_bytes":2*1024**2}}
checks=0
def ok(x):
 global checks
 if not x:raise ValueError('test expectation')
 checks+=1

def reject(fn):
 try:fn()
 except (ValueError,KeyError,TypeError):ok(True);return
 raise ValueError('negative accepted')
# Fixed Yosys stat schema fixture; no real design parsing/native execution.
def row(cells):return {'num_processes':0,'num_cells':sum(cells.values()),'num_cells_by_type':cells}
stages=['HeteroBF16FmaPre','HeteroBF16FmaMul','HeteroBF16FmaPost','HeteroBF16FmaRound']
mods={'\\OrderedQkRealMatrixCore':row({'qwen2_matrix_command_endpoint':8}),'\\qwen2_matrix_command_endpoint':row({'cluster':32}),'\\cluster':row({'lane':16}),'\\lane':row({k:1 for k in stages})}
mods.update({'\\'+k:row({'$and':1}) for k in stages});data={'creator':'Yosys 0.52 (synthetic)','invocation':'stat -json ','modules':mods,'design':row({})}
with tempfile.TemporaryDirectory() as td:
 r=Path(td);(r/'reports').mkdir();(r/'reports/design.json').write_text('{"opaque":"synthetic only"}');(r/'worker.log').write_text('synthetic log\n')
 def run(d):
  (r/'reports/stat.json').write_text(json.dumps(d));return s.structure_check(r,m)
 out=run(data);ok(out['endpoint_count']==8);ok(out['lane_stages_per_endpoint']==512);ok(out['expanded_module_multiplicity']['HeteroBF16FmaPre']==4096)
 for n in [1,7,9]:
  d=copy.deepcopy(data);d['modules']['\\OrderedQkRealMatrixCore']=row({'qwen2_matrix_command_endpoint':n});reject(lambda:run(d))
 for n in [15,17]:
  d=copy.deepcopy(data);d['modules']['\\cluster']=row({'lane':n});reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']=row({'UNKNOWN':1});reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']=row({'cluster':1});reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']['num_cells_by_type']['\\HeteroBF16FmaPre']=1;reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']['num_processes']=1;reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']['num_cells']+=1;reject(lambda:run(d))
 d=copy.deepcopy(data);d['invocation']='stat -width -json ';reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules']['\\lane']=row({'$and':True});reject(lambda:run(d))
 d=copy.deepcopy(data);d['modules'].pop('\\HeteroBF16FmaPre');reject(lambda:run(d))
 run(data);(r/'worker.log').write_text('ERROR: synthetic');reject(lambda:s.structure_check(r,m))
 (r/'worker.log').write_text('ok');(r/'reports/stat.json').write_text('{"x":1,"x":2}');reject(lambda:s.structure_check(r,m))
 (r/'reports/stat.json').write_bytes(b' '*(2*1024**2+1));reject(lambda:s.structure_check(r,m))
 (r/'reports/stat.json').unlink();(r/'reports/stat.json').symlink_to('/dev/null');reject(lambda:s.structure_check(r,m))
print(json.dumps({"status":"PASS_EXTRACTED_STAT_PARSER_SYNTHETIC_ONLY","checks":checks,"native":False,"actual_sv_or_design_read":False}))
