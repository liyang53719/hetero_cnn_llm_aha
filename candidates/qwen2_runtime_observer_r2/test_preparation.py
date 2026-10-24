"""Pure software gates and event fixtures only; never import task runtime/NumPy."""
import copy,importlib.util,os,resource,signal,sys,unittest
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2);resource.setrlimit(resource.RLIMIT_CPU,(20,20));signal.alarm(25)
HERE=Path(__file__).resolve(strict=True).parent
spec=importlib.util.spec_from_file_location('_runtime_observer_preparation',HERE/'runtime_observer.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
if Path(r.__file__).resolve()!=HERE/'runtime_observer.py':raise ImportError('local origin')
def stream(ticket=7,legacy=False):
    events=[('acquire',0,('normal',1))]
    for group in range(2):
        start=group*10+1;tag=group+1;profile=0 if legacy else 2;opcode=0x24 if legacy else 0x23;steps=2
        events.append(('accept_group',start,(opcode,steps,tag,255,profile)))
        events.append(('accept_step',start+1,(0,0,True,False,False,legacy,'a'*64)))
        if legacy:
            events.append(('retire_result',start+2,(0,False,False,ticket+group,0,'d'*64)))
            events.append(('retire_legacy_reply',start+3,(ticket+group,0)))
        events.append(('accept_step',start+4,(1,0,False,True,True,True,'b'*64)))
        events.append(('retire_result',start+5,(0,True,False,ticket+group,0,'e'*64)))
        events.append(('retire_done',start+6,(tag,False,ticket+group,0)))
        if legacy:events.append(('retire_legacy_reply',start+7,(ticket+group,0)))
    events += [('retire_owner_response',30,()),('release',30,())]
    return events

def arm(observe,ticket):
    data={k:0 for k in ('native_fmas','edges','held_checks','owner_clock')}
    data.update(output=(0,),scores=(0,),writes=((0,1,(0,)),),counts={},service_counts={},scalar_calls={},work_events={},lane_calls={},owner_counts={},service_events=stream(ticket),observer_enabled=observe,terminal_acked=True,resources_released=True,capture_report={} if observe else None,capture_error=None,service_trace_error=None)
    return data
class Preparation(unittest.TestCase):
    def reject_change(self,change,legacy=False):
        events=stream(legacy=legacy);change(events)
        with self.assertRaises(ValueError):r.canonical_events(events)
    def test_ticket_renaming_is_only_difference(self):
        for legacy in (False,True):self.assertEqual(r.canonical_events(stream(7,legacy)),r.canonical_events(stream(700,legacy)))
    def test_raw_events_not_modified(self):
        events=stream();before=copy.deepcopy(events);r.canonical_events(events);self.assertEqual(events,before)
    def test_collision_across_groups_rejected(self):
        def change(e):
            for i,(n,t,p) in enumerate(e):
                if n=='retire_result' and p[3]==8:p=list(p);p[3]=7;e[i]=(n,t,tuple(p))
        self.reject_change(change)
    def test_foreign_done_rejected(self):
        self.reject_change(lambda e:e.__setitem__(6,('retire_done',7,(1,False,99,0))))
    def test_wrong_epoch_rejected(self):
        self.reject_change(lambda e:e.__setitem__(6,('retire_done',7,(1,False,7,1))))
    def test_wrong_group_tag_rejected(self):
        self.reject_change(lambda e:e.__setitem__(6,('retire_done',7,(99,False,7,0))))
    def test_duplicate_result_rejected(self):self.reject_change(lambda e:e.insert(6,e[5]))
    def test_duplicate_done_rejected(self):self.reject_change(lambda e:e.insert(7,e[6]))
    def test_step_out_of_order_rejected(self):self.reject_change(lambda e:e.__setitem__(2,('accept_step',2,(1,0,False,False,False,False,'a'*64))))
    def test_overlap_group_rejected(self):self.reject_change(lambda e:e.insert(3,('accept_group',3,(0x23,2,2,255,2))))
    def test_early_done_rejected(self):self.reject_change(lambda e:e.insert(3,('retire_done',3,(1,False,7,0))))
    def test_duplicate_legacy_reply_rejected(self):self.reject_change(lambda e:e.insert(5,e[4]),True)
    def test_foreign_legacy_reply_rejected(self):self.reject_change(lambda e:e.__setitem__(4,('retire_legacy_reply',4,(99,0))),True)
    def test_unreleased_owner_rejected(self):self.reject_change(lambda e:e.pop())
    def test_early_terminal_rejected(self):self.reject_change(lambda e:e.insert(3,('retire_owner_response',3,())))
    def test_identical_arms_pass(self):r.compare_arms([arm(False,7),arm(True,70)])
    def test_observation_failure_preserves_objects_but_rejects_acceptance(self):
        arms=[arm(False,7),arm(True,70)];arms[1]['capture_error']='missing field';before=copy.deepcopy(arms)
        with self.assertRaises(ValueError):r.compare_arms(arms)
        self.assertEqual(arms,before)
    def test_changed_writes_rejected(self):
        arms=[arm(False,7),arm(True,70)];arms[1]['writes']=()
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_service_event_packet_change_rejected(self):
        arms=[arm(False,7),arm(True,70)];e=arms[1]['service_events'];n,t,p=e[2];e[2]=(n,t,(*p[:-1],'c'*64))
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_full_result_hash_change_rejected(self):
        arms=[arm(False,7),arm(True,70)];e=arms[1]['service_events'];n,t,p=e[5];e[5]=(n,t,(*p[:-1],'f'*64))
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_lane_call_change_rejected(self):
        arms=[arm(False,7),arm(True,70)];arms[1]['lane_calls']={'add':1}
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_owner_counter_change_rejected(self):
        arms=[arm(False,7),arm(True,70)];arms[1]['owner_counts']={'extra':1}
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_clock_change_rejected(self):
        arms=[arm(False,7),arm(True,70)];arms[1]['owner_clock']=1
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_missing_terminal_rejected(self):
        arms=[arm(False,7),arm(True,70)];arms[0]['terminal_acked']=False
        with self.assertRaises(ValueError):r.compare_arms(arms)
    def test_no_runtime_imported(self):
        self.assertNotIn('numpy',sys.modules)
        self.assertFalse(any(n.startswith('candidates.qwen2_resident_matrix') for n in sys.modules))
if __name__=='__main__':unittest.main()
