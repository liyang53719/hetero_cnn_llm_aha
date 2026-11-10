"""Independent ordered FP32 equations for phase6-17; never hardware responses."""
def compute(n,q,k,v,g,b,initial):
 add,mul,sub=(n[x] for x in ('add','mul','sub'))
 mm,trans,point,scale,solve=(n[x] for x in ('matmul','transpose','pointwise','scale_rows','lower_solve'))
 c=n['cumulative'](g,0);exp=n['exp_negative'];e=[exp(x,0) for x in c]
 remain=[exp(sub(c[-1],x),0) for x in c];decay=exp(c[-1],0)
 kb=scale(k,b);vb=scale(v,b);kbg=scale(kb,e);qg=scale(q,e);ke=scale(k,remain)
 pair=[[exp(sub(c[i],c[j]),0) if j<=i else 0.0 for j in range(64)] for i in range(64)]
 ut=point(mm(kb,trans(k)),pair,mul)
 intra=point(mm(q,trans(k)),pair,mul)
 solvev=solve(ut,vb);solvek=solve(ut,kbg)
 pred=mm(solvek,initial);vnew=point(solvev,pred,sub)
 inter=mm(qg,initial);local=mm(intra,vnew);out=point(inter,local,add)
 update=mm(trans(ke),vnew);decayed=[[mul(x,decay) for x in row] for row in initial]
 state=point(decayed,update,add)
 return {"cumulative":c,"decay":decay,"derived":{"kb":kb,"vb":vb,"kbg":kbg,"qg":qg,"ke":ke,"pair":pair,"kt":trans(k),"ket":trans(ke)},"phases":{5:ut,6:intra,7:solvev,8:solvek,9:pred,10:vnew,11:inter,12:local,13:out,14:update,15:decayed,16:state,17:out}}
