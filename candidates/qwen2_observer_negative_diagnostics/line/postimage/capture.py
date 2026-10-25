"""New observation semantics over the unchanged ten-field PackedFields buffers."""
def need(ok,message):
    if not ok:raise ValueError(message)

class Fields:
    def __init__(self,base):
        self.base=base;self.fields=base.fields;self.rows=base.rows
        self.work={};self.completed=[];self.accepted={};self.commits={};self.terminal=None
        self.acks=0;self.dones=0;self.prob_columns={}
    def bind(self,work,h,t,first,count):
        key=id(work)
        if key not in self.work:
            need(0<=h<12 and 0<=t<self.rows and 0<=first<=t and first%16==0 and count==min(16,t+1-first),'work coordinates')
            self.work[key]=dict(object=work,h=h,t=t,first=first,count=count,scale={},retired=0)
        a=self.work[key];need((a['h'],a['t'],a['first'],a['count'])==(h,t,first,count),'work coordinate drift')
        return a
    def parts(self,work,row,values):
        a=self.work[id(work)];need(0<=row<16 and len(values)==a['count'],'valid stripe')
        for j,value in enumerate(values):self.base._put('dot_parts',(a['h'],a['t'],a['first']+j,row),(value,))
    def scale(self,work,j,total,dot,score):
        a=self.work[id(work)];need(0<=j<a['count'] and j not in a['scale'],'duplicate/speculative scale')
        a['scale'][j]=(total,dot,score)
    def consume(self,work,retired,result):
        a=self.work[id(work)];need(id(work) not in self.accepted,'duplicate consume');need(result is True and retired.work is work and retired.key==a['retired'],'ordered accepted retirement')
        need(not retired.error and retired.key in a['scale'],'fault or missing computed scale')
        need(a['scale'][retired.key][2]==retired.score,'retired score differs from actual computed score')
        self.accepted[id(work)]=retired
    def commit(self,work,retired,scores):
        a=self.work[id(work)];j=retired.key;k=a['first']+j;position=(a['h'],a['t'])
        need(self.accepted.pop(id(work),None) is retired and j==a['retired'],'commit without consume or duplicate')
        need(self.commits.get(position,0)==k and len(scores)==k+1 and scores[-1]==retired.score,'score prefix changed')
        for name,value in zip(('unrounded_dot_sum','dot_bf16','scores_bf16'),a['scale'][j]):self.base._put(name,(a['h'],a['t'],k),(value,))
        a['retired']+=1;self.commits[position]=k+1
    def single(self,name,coordinates,values):self.base._put(name,coordinates,values)
    def probability(self,h,t,k,col,fp,bf):
        need(col in range(0,128,16),'PV column');key=(h,t,k);seen=self.prob_columns.setdefault(key,set())
        need(col not in seen and col==len(seen)*16,'PV probability column duplicate/order')
        index=(h*self.rows*self.rows+t*self.rows+k)
        for name,value in (('softmax_fp32',fp),('prob_bf16',bf)):
            f=self.fields[name]
            if not seen:self.base._put(name,(h,t,k),(value,))
            else:
                need(f['observed'][index] and f['words'][index]==value,'actual repeated probability drift')
                f['frequency'][index]+=1;f['repeats']+=1
        seen.add(col)
    def release(self,work):
        a=self.work[id(work)]
        need(a.get('ack') and a.get('done') and a['retired']==a['count'] and id(work) not in self.accepted,'release before actual retirement')
        del self.work[id(work)];a.pop('object');a.pop('scale');self.completed.append(a)
    def seal(self):
        need(self.terminal is not None and self.terminal['clean'],'no clean accepted terminal')
        need(not self.accepted and not self.work,'unfinished work retirement')
        need(self.acks==self.dones==len(self.completed) and all(a.get('ack') and a.get('done') for a in self.completed),'actual packed ACK/done coverage')
        m=self.rows
        need(set(self.fields)=={'dot_parts','unrounded_dot_sum','dot_bf16','scores_bf16','softmax_exp','softmax_fp32','prob_bf16','normalizer','pv_raw','pv_bf16'},'exact ten field set required')
        for name,f in self.fields.items():
            width=16 if name=='dot_parts' else 3 if name=='normalizer' else 128 if name in ('pv_raw','pv_bf16') else 1
            shape=(12,m,m,16) if name=='dot_parts' else (12,m,3) if name=='normalizer' else (12,m,128) if name in ('pv_raw','pv_bf16') else (12,m,m)
            count=1
            for n in shape:count*=n
            need(f['shape']==shape and all(len(f[key])==count for key in ('words','observed','frequency')),'field shape or buffer extent changed')
            for h in range(12):
                for t in range(m):
                    keys=(None,) if name in ('normalizer','pv_raw','pv_bf16') else range(m)
                    for k in keys:
                        start=((h*m+t) if k is None else (h*m*m+t*m+k))*width;present=k is None or k<=t
                        expected=(8 if name in ('softmax_fp32','prob_bf16') else 1) if present else 0
                        for i in range(start,start+width):
                            need(f['observed'][i]==int(present) and f['frequency'][i]==expected,'missing/duplicate observed intermediate '+name)
                            need(present or f['words'][i]==0xa5963cc3,'future cell modified')
            observed=sum(f['observed']);need(f['writes']==observed and f['repeats']==(7*observed if name in ('softmax_fp32','prob_bf16') else 0),'field event accounting')
        need(all(len(cols)==8 for cols in self.prob_columns.values()),'missing legacy PV probability reuse')
        return dict(status='COMPLETE_SOFTWARE_OBSERVATION_NOT_HARDWARE',fields=self.base.field_summary(),packed_acks=self.acks,packed_done=self.dones,terminal=self.terminal,model_steps_are_cycles=False)
