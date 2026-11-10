from run import *
t=time.monotonic()
tr=data('trig');c=fp(tr[:,None,:32]);s=fp(tr[:,None,32:]);reports.clear()
for n,h in [('q',8),('k',2)]:
 x=arr(n+'n');a=fp(x[...,:32]);b=fp(x[...,32:64]);y=x.copy()
 ac=fp(bf(op(a,c,'mul')));bs=fp(bf(op(b,s,'mul')));ass=fp(bf(op(a,s,'mul')));bc=fp(bf(op(b,c,'mul')))
 y[...,:32]=bf(op(ac,-bs,'add'));y[...,32:64]=bf(op(ass,bc,'add'));same(n+'rope',y,arr(n+'r'))
r=dict(status='PASS_FULL_REAL_M128_PARTIAL_ROPE_PRIMITIVES_MATH_ONLY',reports=reports,scalar_nodes_flags=dict(counts),verified_inputs=pins,seconds=time.monotonic()-t,limits=['No hardware','BF16 conversion exception mapping unqualified; conversion values match','Last192dimensions copied'])
(R/'ROPE_PROGRESS.json').write_text(json.dumps(reports,indent=2));(R/'PROGRESS.json').write_text(json.dumps(json.loads((R/'RESULT.json').read_text())['reports'],indent=2));(R/'ROPE_RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
