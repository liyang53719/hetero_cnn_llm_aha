"""Test-only port inventory + mechanically preserved B protocol driver; no native load."""
import argparse,hashlib,json,re
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def inventory(low,harness):
    top='Public21DownOwnerProtocolHarness';ports=[];header=[];found=False
    for line in low:
        if line.startswith('  module '+top+' :'):
            if found:raise ValueError('duplicate top')
            found=True;header.append(line);continue
        if not found:continue
        if not line.strip():continue
        m=re.fullmatch(r'    (input|output) (\w+) : (Clock|UInt<\d+>|SInt<\d+>)(?: @.*)?\n?',line)
        if not m:break
        direction,name,typ=m.groups();header.append(line)
        ports.append(dict(name=name,direction=direction,width=1 if typ=='Clock' else int(re.search(r'\d+',typ).group()),signed=typ.startswith('SInt'),clock=typ=='Clock'))
    if not found or not ports:raise ValueError('missing top ports')
    if len({p['name'] for p in ports})!=len(ports):raise ValueError('duplicate port')
    clocks=[p for p in ports if p['clock']]
    if clocks!=[dict(name='clock',direction='input',width=1,signed=False,clock=True)]:raise ValueError('clock contract')
    ordered=[p for d in ('input','output') for p in ports if p['direction']==d and not p['clock']]
    def part(start,end):
        if harness.count(start)!=1 or harness.count(end)!=1:raise ValueError('harness section uniqueness')
        return harness.split(start)[1].split(end)[0]
    ps=part('inline void poke(int32_t id, int64_t value)', 'inline int64_t peek(int32_t id)')
    qs=part('inline int64_t peek(int32_t id)', 'inline void poke_wide(int32_t id, int32_t offset, int64_t value)')
    pw=part('inline void poke_wide(int32_t id, int32_t offset, int64_t value)','inline int64_t peek_wide(int32_t id, int32_t offset)')
    qw=part('inline int64_t peek_wide(int32_t id, int32_t offset)','inline void set_args')
    def parse(s,pattern):
        rows=re.findall(pattern,s)
        if len(rows)!=len(re.findall(r'case \d+\s*:',s)):raise ValueError('unparsed switch case')
        ids=[int(r[0]) for r in rows]
        if len(set(ids))!=len(ids):raise ValueError('duplicate harness ID')
        return {int(r[0]):r[1:] for r in rows}
    sp=parse(ps,r'case (\d+) : dut->(\w+) = u; break;')
    sq=parse(qs,r'case (\d+) : value = dut->(\w+); break;')
    wp=parse(pw,r'case (\d+) : data = dut->(\w+); words = (\d+); break;')
    wq=parse(qw,r'case (\d+) : data = dut->(\w+); words = (\d+); break;')
    expected={i:(p['name'],) for i,p in enumerate(ordered) if p['width']<=64}
    wide={i:(p['name'],str((p['width']+31)//32)) for i,p in enumerate(ordered) if p['width']>64}
    if sq!=expected or wq!=wide:raise ValueError('peek ID/name/width mapping')
    if sp!={i:r for i,r in expected.items() if ordered[i]['direction']=='input'}:raise ValueError('poke direction/scalar mapping')
    if wp!={i:r for i,r in wide.items() if ordered[i]['direction']=='input'}:raise ValueError('poke direction/wide mapping')
    if 'top->clock = 0;' not in harness or 'top->clock = 1;' not in harness:raise ValueError('clock implementation')
    return dict(schema='B_DIRECT_JNA_PORT_INVENTORY_V1',scope='PROTOCOL_FIXTURE_ONLY_NOT_NUMERICAL',top=top,clocks=['clock'],ports=[dict(id=i,**p) for i,p in enumerate(ordered)],harness_sha256=sha(harness.encode()),top_header_sha256=sha(''.join(header).encode()))

def verify_sv(lines,inv):
    found=False;rows=[];header=[]
    for line in lines:
        if line.startswith('module '+inv['top']+'('):found=True;header.append(line);continue
        if not found:continue
        if line.strip()==');':header.append(line);break
        m=re.fullmatch(r'  (input|output)\s+(?:\[(\d+):0\]\s+)?(\w+),?\s*(?://.*)?\n?',line)
        if not m:raise ValueError('unknown SV port declaration')
        d,w,n=m.groups();rows.append((n,d,int(w)+1 if w is not None else 1));header.append(line)
    if not found:raise ValueError('SV top missing')
    expected=[(p['name'],p['direction'],p['width']) for p in inv['ports']]+[('clock','input',1)]
    if len(rows)!=len(set(n for n,d,w in rows)) or sorted(rows)!=sorted(expected):raise ValueError('SV/LOW exact name/direction/width mismatch')
    return sha(''.join(header).encode())

def verify_expected(inv,expected):
    if set(expected)!={'schema','top','clocks','port_count','typed_inventory_sha256'} or expected['schema']!='B_EXPECTED_TYPED_PORT_DIGEST_V1':raise ValueError('expected typed schema')
    body={k:inv[k] for k in ('top','clocks','ports')}
    digest=sha(json.dumps(body,sort_keys=True,separators=(',',':')).encode())
    if inv['top']!=expected['top'] or inv['clocks']!=expected['clocks'] or len(inv['ports'])!=expected['port_count'] or digest!=expected['typed_inventory_sha256']:raise ValueError('cloud typed ports differ from original 4710 inventory')

def driver(source):
    start=source.index('  val path=');end=source.index('  "Real selected DownOwner')
    old=source[start:end]
    a='def run(d:Public21DownOwnerProtocolHarness):Unit='
    b='def fire(x:chisel3.util.DecoupledIO[_]):Boolean='
    if old.count(a)!=1 or old.count(b)!=1:raise ValueError('driver substitution uniqueness')
    body=old.replace(a,'def run(d:DirectDut):Unit=').replace(b,'def fire(x:DirectPort):Boolean=')
    if body.replace('def run(d:DirectDut):Unit=',a).replace('def fire(x:DirectPort):Boolean=',b)!=old:raise ValueError('inverse driver mismatch')
    pre='''// Generated test-only driver. Original protocol body preserved except two types.
package heteronpu.continuous
import chisel3._
import org.scalatest.matchers.should.Matchers
import java.nio.file.{Files,Paths}
import java.security.MessageDigest
import scala.collection.mutable
import scala.language.dynamics
class Public21DownOwnerDirectDriver extends Matchers {
  def zero(x:DirectPort):Unit=x.zero()
'''
    return pre+body+'}\n',dict(original_spec_sha256=sha(source.encode()),original_body_sha256=sha(old.encode()),adapted_body_sha256=sha(body.encode()),reversible_type_substitutions=2)

def main():
    a=argparse.ArgumentParser();a.add_argument('--low',type=Path,required=True);a.add_argument('--harness',type=Path,required=True);a.add_argument('--spec',type=Path,required=True);a.add_argument('--sv',type=Path,required=True);a.add_argument('--output',type=Path,required=True);a.add_argument('--expected-ports',type=Path,required=True);n=a.parse_args()
    with n.low.open() as f: inv=inventory(f,n.harness.read_text())
    with n.sv.open() as f:inv['sv_header_sha256']=verify_sv(f,inv)
    verify_expected(inv,json.loads(n.expected_ports.read_text()))
    text,proof=driver(n.spec.read_text());inv.update(proof)
    n.output.mkdir(exist_ok=True)
    for name,data in [('PORTS.json',json.dumps(inv,indent=2)+'\n'),('Public21DownOwnerDirectDriver.scala',text)]:
        with (n.output/name).open('x') as f:f.write(data)
if __name__=='__main__':main()
