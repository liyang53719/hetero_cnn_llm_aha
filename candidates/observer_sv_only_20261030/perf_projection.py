import json,pathlib,resource,sys,time,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
try:
 import sv_difference_projection as p
except ModuleNotFoundError:
 import project_key_ports as p
name=p.MODULES[1];ports,assigns=p.contract(name)
header='module '+name+'(\ninput clock,\noutput [31:0] result,\n'+',\n'.join(f'{d} [{w-1}:0] {n}'for n,(d,w)in ports.items())+'\n);\n'
body='\n'.join(f'assign {d} = {s};'for d,s in assigns.items())+'\n'
rows=[];total=len(header)+len(body)+len('endmodule\n')
i=0
while total<8*1024**2-100:
 line=f"wire [31:0] w{i}; assign w{i} = 32'h0;\n";rows.append(line);total+=len(line);i+=1
raw=(header+body+''.join(rows)+'endmodule\n').encode();del rows
start=time.monotonic()
with tempfile.TemporaryFile(dir=pathlib.Path.cwd())as sink:r=p.projected_hash(raw,name,True,sink=sink)
elapsed=time.monotonic()-start
print(json.dumps(dict(schema='SYNTHETIC_PROJECTION_PERFORMANCE_V1',input_bytes=len(raw),elapsed_seconds=elapsed,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,projected_bytes=r['projected_normalized_bytes'],actual_sv_proof=False,numerical_pass=False)))
