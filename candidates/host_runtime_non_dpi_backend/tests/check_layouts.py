from itertools import product
import json
cases=0
for shape in product(range(1,4),repeat=3):
 for strides in product(range(1,10),repeat=3):
  for eb in (1,2,4):
   order=sorted(range(3),key=lambda i:-strides[i]);inner=eb;valid=True
   for i in reversed(order):
    if shape[i]>1:
     if strides[i]<inner:valid=False;break
     inner+=(shape[i]-1)*strides[i]
   if not valid:continue
   exact={sum(c[i]*strides[i] for i in range(3))+b:(c,b) for c in product(*(range(n) for n in shape)) for b in range(eb)}
   expected_bytes=eb
   for n in shape:expected_bytes*=n
   if len(exact)!=expected_bytes:raise ValueError('admitted self overlap')
   end=sum((shape[i]-1)*strides[i] for i in range(3))+eb
   for a in range(end):
    rem=a;cs=[0]*3;accept=True
    for i in order:
     if shape[i]==1:continue
     cs[i]=rem//strides[i]
     if cs[i]>=shape[i]:accept=False;break
     rem%=strides[i]
    accept=accept and rem<eb
    if accept != (a in exact) or accept and (tuple(cs),rem)!=exact[a]:raise ValueError((shape,strides,eb,a))
   cases+=1
print(json.dumps({'status':'PASS_ABSTRACT_LAYOUT_MODEL_NOT_CPP_OR_DUT','valid_layouts':cases,'rank':3,'shape_range':[1,3],'stride_range':[1,9],'element_bytes':[1,2,4]}))
