"""Generate local synthetic stimulus; never publish the generated word payload."""
import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
pins=json.loads((R/'ORACLE_PINS.json').read_text())
source=(R/'scalar_core.py').read_bytes()
assert hashlib.sha256(source).hexdigest()==pins['scalar_core.py']
namespace={};exec(compile(source,str(R/'scalar_core.py'),'exec'),namespace)
fixture,bits,cumulative=(namespace[n] for n in ('fixture','bits','cumulative'))
q,k,v,g,b,_=fixture()
with (R/'Fixture.scala').open('w') as f:
 f.write('object Fixture {\n')
 for name,rows in [('q',q),('k',k),('v',v),('g',[g]),('beta',[b]),('p0',[cumulative(g[:64],0)+cumulative(g[64:],0)]),('p1',[cumulative(g[:64],1)+cumulative(g[64:],1)])]:
  f.write('val '+name+' = Vector('+','.join(name+str(i)+'()' for i in range(len(rows)))+')\n')
  for i,row in enumerate(rows):f.write('def '+name+str(i)+'() = Vector('+','.join(str(bits(x))+'L' for x in row)+')\n')
 f.write('}\n')
