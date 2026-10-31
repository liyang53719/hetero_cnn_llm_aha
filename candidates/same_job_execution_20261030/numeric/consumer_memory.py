"""Cloud diagnostic consumer/DUT address-space envelope. No DUT arithmetic.
Before fork: parent soft512MiB, hard inherited DUT ceiling. Child sets its own
original preexec limits. Immediately after Popen (also failure): parent hard512MiB.
RSS group watchdog is sampled, not a cgroup hard memory-isolation guarantee.
"""
import pathlib,resource
_ACTIVE=None

def need(v,m):
 if not v:raise ValueError(m)
def virtual_bytes():
 fields=[x for x in pathlib.Path('/proc/self/status').read_text().splitlines()if x.startswith('VmSize:')]
 need(len(fields)==1,'actual current consumer VmSize');return int(fields[0].split()[1])*1024

def prepare(parent_bytes,dut_bytes):
 global _ACTIVE
 need(_ACTIVE is None,'one immutable consumer memory admission')
 need(type(parent_bytes)is int and parent_bytes==512<<20,'reviewed consumer512MiB soft then hard envelope')
 need(type(dut_bytes)is int and parent_bytes<=dut_bytes<=12<<30,'finite original-or-smaller DUT address space')
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 need(hard==resource.RLIM_INFINITY or dut_bytes<=hard,'never raise inherited hard address-space ceiling')
 need(virtual_bytes()<parent_bytes,'consumer metadata already exceeds reviewed envelope')
 # Prepare occurs before full frozen-artifact parsing and reference reads.
 resource.setrlimit(resource.RLIMIT_AS,(parent_bytes,dut_bytes));_ACTIVE=(parent_bytes,dut_bytes)
 return dict(consumer_pre_fork_soft_bytes=parent_bytes,consumer_pre_fork_hard_bytes=dut_bytes,consumer_after_popen_hard_bytes=parent_bytes,dut_hard_address_space_bytes=dut_bytes,group_rss_is_sampled=True)

def after_popen():
 if _ACTIVE is not None:
  parent,_=_ACTIVE
  resource.setrlimit(resource.RLIMIT_AS,(parent,parent))
