"""Owning-flow continuous preparation accounting, never a new execution lease.
Native stage caps reserve cleanup. Python checks are boundary-sampled, not a
zero-overshoot hard timer; the existing supervisor retains signal ownership.
"""
import math,time
SCHEMA='SAME_JOB_HOST_DIAGNOSTIC_CONTINUOUS_PREPARATION_V1'
JOB=21000;CONTROL=300;BUILD=7200;PREP=3600;TAIL=900;MIN_DUT=9000

def need(v,m):
 if not v:raise ValueError(m)
def number(x):return type(x)in(int,float)and math.isfinite(x)
class PreparationBudget:
 def __init__(self,started,control_done,clock=time.monotonic):
  self.clock=clock;need(number(started)and number(control_done)and 0<=control_done-started<=CONTROL,'bounded original control interval')
  self.started=started;self.control_done=control_done;self.build_start=None;self.build_end=None;self.frozen=False;self.check()
 def build_seconds(self):return 0 if self.build_end is None else self.build_end-self.build_start
 def elapsed(self):
  now=self.clock();need(number(now)and now>=self.control_done,'monotonic owning clock');return now-self.started
 def charged(self):return self.elapsed()-(self.control_done-self.started)-self.build_seconds()
 def check(self):
  need(not self.frozen,'preparation already frozen')
  need(self.build_start is None or self.build_end is not None,'preparation cannot run during build')
  need(self.elapsed()<=JOB-TAIL-MIN_DUT,'no remaining long-DUT reservation')
  need(0<=self.charged()<=PREP,'continuous preparation limit including checks/gaps')
 def cap(self,name,seconds,cleanup=30):
  need(type(name)is str and name and type(seconds)is int and seconds>0 and type(cleanup)is int and cleanup>=0,'finite actual preparation stage')
  self.check();remaining=min(PREP-self.charged(),JOB-TAIL-MIN_DUT-self.elapsed())
  cap=min(seconds,math.floor(remaining-cleanup));need(cap>0,'no preparation and cleanup reservation for '+name);return cap
 def begin_build(self):
  self.check();need(self.build_start is None,'single build only');self.build_start=self.clock()
 def end_build(self):
  need(self.build_start is not None and self.build_end is None,'one actual build interval')
  self.build_end=self.clock();need(number(self.build_end)and 0<=self.build_seconds()<=BUILD,'actual build interval limit');self.check()
 def snapshot(self):
  self.check();need(self.build_end is not None,'actual build required')
  return dict(schema=SCHEMA,job_started_monotonic=self.started,control_done_monotonic=self.control_done,build_started_monotonic=self.build_start,build_ended_monotonic=self.build_end,checks_are_boundary_sampled=True,preparation_limit_seconds=PREP,build_limit_seconds=BUILD)
 def freeze(self):
  self.check();need(self.build_end is not None,'actual build completed');now=self.clock();window=min(14400,math.floor(JOB-(now-self.started)-TAIL));need(window>=MIN_DUT,'no short fallback')
  state=self.snapshot();self.frozen=True
  return dict(schema='REAL_FULLTOP_P0_M128_LONG_HOST_DIAGNOSTIC_V1',preparation=state,job_started_monotonic=self.started,frozen_at_monotonic=now,dut_wall_seconds=window,dut_deadline_monotonic=now+window,tail_deadline_monotonic=min(self.started+JOB,now+window+TAIL),job_deadline_monotonic=self.started+JOB,max_active_cycles=3000000,charged_preparation_elapsed_seconds=now-self.control_done-self.build_seconds(),dut_cpu_seconds=window,supervisor_cpu_seconds=window+120,combined_dut_phase_cpu_seconds=2*window+120,extends_existing_lease=False,restart_allowed=False,full_block_acceptance=False)
