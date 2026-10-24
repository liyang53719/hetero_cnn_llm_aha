"""Normal-source factory and source-bound, passive Matrix event recording.

Constructed only inside a separately authorized real component attempt.
"""
import hashlib,importlib,importlib.util,struct,sys,threading,types
from pathlib import Path

def need(ok,message):
    if not ok:raise ValueError(message)
def load_observer(config):
    root=Path(config['observer_root']).resolve(strict=True)
    package=types.ModuleType('_qualified_runtime_observer');package.__path__=[str(root)];sys.modules[package.__name__]=package
    monitor=importlib.import_module(package.__name__+'.monitor')
    path=Path(config['buffer_source']).resolve(strict=True)
    spec=importlib.util.spec_from_file_location('_qualified_runtime_fields',path);base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
    need(Path(monitor.__file__).resolve()==root/'monitor.py' and Path(base.__file__).resolve()==path,'observer import origin')
    return monitor,base

def bindings(owner,config):
    from candidates.qwen2_resident_matrix.production_qk16_model.ordered_work import OrderedFoldWork
    from candidates.qwen2_resident_matrix.attention_packed_owner.client import PackedClient
    root=Path(config['source_root'])/'candidates/qwen2_resident_matrix'
    specs={
        'run':(owner.packed_schedule.run,'production_qk16_model/schedule.py','ProductionQk16Schedule','run'),
        'work':(owner.ordered_adapter.tick,'production_qk16_model/ordered_work.py','OrderedFoldAdapter','tick'),
        'consume':(OrderedFoldWork.consume,'production_qk16_model/ordered_work.py','OrderedFoldWork','consume'),
        'matrix':(owner._matrix_step,'ffn_attention/attention_owner.py','AttentionOwner','_matrix_step'),
        'op':(owner._op,'ffn_attention/attention_owner.py','AttentionOwner','_op'),
        'tick':(owner.tick,'ffn_attention/attention_owner.py','AttentionOwner','tick'),
        'client':(PackedClient.tick,'attention_packed_owner/client.py','PackedClient','tick')}
    return {role:(fn,root/path,config['files'][str(root/path)]['sha256'],cls,name) for role,(fn,path,cls,name) in specs.items()}

class ServiceTrace:
    """Same tracer in both arms; no service property/native calls from callback."""
    METHODS=('acquire','accept_group','accept_step','retire_result','retire_done','retire_legacy_reply','retire_owner_response','release','abort')
    def __init__(self,service,config,bind):
        self.service=service;self.events=[];self.error=None;self.tool=None;self.closed=False;self.thread=threading.get_ident()
        path=Path(config['source_root'])/'candidates/qwen2_resident_matrix/ffn_attention/matrix_service.py';pin=config['files'][str(path)]['sha256']
        self.codes={bind(getattr(service,name),path,pin,'MatrixService',name,False):name for name in self.METHODS}
    def __enter__(self):
        m=sys.monitoring
        for tool in (4,3):
            if m.get_tool(tool) is None and not m.get_events(tool):self.tool=tool;break
        need(self.tool is not None,'service trace tool unavailable');m.use_tool_id(self.tool,'ordered-service-events')
        m.register_callback(self.tool,m.events.PY_RETURN,self._return)
        for code in self.codes:m.set_local_events(self.tool,code,m.events.PY_RETURN)
        return self
    def stop(self):
        if self.tool is not None:
            m=sys.monitoring
            for code in self.codes:m.set_local_events(self.tool,code,0)
            m.register_callback(self.tool,m.events.PY_RETURN,None);m.free_tool_id(self.tool);self.tool=None
        self.closed=True
    def __exit__(self,*error):self.stop();return False
    def _return(self,code,offset,result):
        try:
            frame=sys._getframe(1);a=frame.f_locals
            if a.get('self') is not self.service:return
            need(threading.get_ident()==self.thread,'service trace thread changed')
            name=self.codes[code]
            if name in ('acquire','accept_group','accept_step') and result is not True:return
            owner=a.get('owner');edge=getattr(owner,'clock',None)
            if name=='acquire':payload=(a['mode'],a['tag'])
            elif name=='accept_group':
                g=a['group'];payload=(g.opcode,g.steps,g.tag,g.slice_mask,g.profile)
            elif name=='accept_step':
                s=a['step'];payload=(s.index,s.context,s.clear,s.last,s.finish,s.emit,hashlib.sha256(struct.pack('<272H',*s.a,*s.b)).hexdigest())
            elif name=='retire_result':
                r=a['result'];need(type(r.value.raw) is bytes and len(r.value.raw)==16384,'complete immutable result payload');payload=(r.context,r.last,r.error,r.ticket,r.epoch,hashlib.sha256(r.value.raw).hexdigest())
            elif name=='retire_done':
                d=a['done'];payload=(d.tag,d.error,d.ticket,d.epoch)
            elif name=='retire_legacy_reply':payload=(a['ticket'],a['epoch'])
            else:payload=()
            self.events.append((name,edge,payload))
        except Exception as error:
            self.error=type(error).__name__+': '+str(error);self.stop()
    def seal(self):
        need(self.closed and self.error is None,'service trace failed or still active');return tuple(self.events)

def compare_arms(arms):
    need(len(arms)==2 and [a['observer_enabled'] for a in arms]==[False,True],'off/on observer arms required')
    need(all(a['terminal_acked'] and a['resources_released'] for a in arms),'both actual terminal ACKs required')
    # A collector failure must not turn a completed workload into accepted evidence.
    need(arms[1]['capture_error'] is None and arms[1]['capture_report'] is not None,'capture failed; completed DUT is not qualification')
    need(all(a['service_trace_error'] is None for a in arms),'service event trace failed')
    keys=('output','scores','writes','counts','service_counts','scalar_calls','native_fmas','edges','held_checks','work_events','lane_calls','owner_counts','owner_clock')
    for key in keys:need(arms[0][key]==arms[1][key],'observer perturbed '+key)
    need(canonical_events(arms[0]['service_events'])==canonical_events(arms[1]['service_events']),'observer perturbed canonical service events')
    return {'ticket_policy':'only native ticket first-appearance alpha-renaming; raw events retained','status':'PASS_EXACT_OFF_ON_CONTROL_EQUIVALENCE','compared':keys}

def canonical_events(events):
    """Validate each actual lifecycle, then alpha-rename only native tickets.

    Raw stream remains intact. A ticket cannot be reused by a later group,
    merged with another live group, or introduced by a done/legacy reply.
    """
    tickets={};out=[];last_ticket=None;active=None;owned=False;terminal=False;released=False;last_edge=-1
    for name,edge,raw_values in events:
        need(type(edge) is int and edge>=last_edge,'service event edge order');last_edge=edge
        values=list(raw_values);need(not released,'event after owner release')
        if name=='acquire':
            need(not owned and not terminal and values[0]=='normal','duplicate/non-normal acquire');owned=True
        else:need(owned,'service event without owner')
        if name=='accept_group':
            need(active is None and not terminal,'overlapping group')
            opcode,steps,tag,mask,profile=values
            need((opcode,profile) in ((0x23,2),(0x24,0)) and type(steps) is int and steps>0,'unexpected group profile')
            active=dict(steps=steps,tag=tag,profile=profile,index=0,pending=None,reply=False,done=False,ticket=None,epoch=None)
        elif name=='accept_step':
            need(active is not None and not active['done'] and active['pending'] is None and not active['reply'],'step overlaps debt')
            index,context,clear,last,finish,emit,packet_hash=values
            need(index==active['index']<active['steps'] and clear==(index==0) and last==(index+1==active['steps']) and finish==last,'step order/boundary')
            need(emit==(last if active['profile']==2 else True),'profile result emission')
            active['index']+=1
            if emit:active['pending']=(context,last)
        elif name=='retire_result':
            need(active is not None and active['pending'] is not None and not active['done'],'duplicate/foreign result')
            context,last,error,ticket,epoch,result_hash=values
            need((context,last)==active['pending'] and error is False,'result metadata/error')
            need(type(ticket) is int and ticket>0 and type(epoch) is int and epoch>=0,'ticket/epoch type')
            if active['ticket'] is None:
                need(ticket not in tickets and (last_ticket is None or ticket>last_ticket),'ticket collision/reuse/order')
                tickets[ticket]=len(tickets)+1;last_ticket=ticket;active['ticket']=ticket;active['epoch']=epoch
            need(ticket==active['ticket'] and epoch==active['epoch'],'result belongs to different group')
            values[3]=tickets[ticket];active['pending']=None;active['reply']=active['profile']==0
        elif name=='retire_done':
            need(active is not None and not active['done'] and active['index']==active['steps'] and active['pending'] is None,'early/duplicate done')
            tag,error,ticket,epoch=values
            need(ticket==active['ticket'] and epoch==active['epoch'] and tag==active['tag'] and error is False,'foreign done')
            values[2]=tickets[ticket];active['done']=True
            if active['profile']==2:active=None
        elif name=='retire_legacy_reply':
            need(active is not None and active['profile']==0 and active['reply'] and active['pending'] is None,'duplicate/foreign legacy reply')
            ticket,epoch=values
            need(ticket==active['ticket'] and epoch==active['epoch'],'legacy reply belongs to different group')
            need(active['index']<active['steps'] or active['done'],'final legacy reply before done')
            values[0]=tickets[ticket];active['reply']=False
            if active['done']:active=None
        elif name=='retire_owner_response':
            need(active is None and not terminal,'terminal before group debt/duplicate');terminal=True
        elif name=='release':
            need(active is None and terminal,'release before terminal');released=True;owned=False
        elif name=='abort':raise ValueError('aborted stream is not accepted equivalence')
        else:need(name=='acquire','unknown service event')
        out.append((name,edge,tuple(values)))
    need(released and terminal and active is None and not owned,'incomplete service lifecycle')
    return tuple(out)
