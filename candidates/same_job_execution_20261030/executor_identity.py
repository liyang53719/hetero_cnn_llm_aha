"""Cloud executor identity only; no builder/GitHub identity or execution authority.
Validation does not attest the supplied host digest or create an execution.
verify_owner observes the live original controller; verify_current also binds self.
"""
import math
import os
import pathlib
import re
import time
import uuid

FIELDS={'schema','source_commit','execution_id','boot_id','controller_pid','start_tick','host_identity_sha256','started_monotonic'}

def need(value, message):
    if not value:
        raise ValueError(message)

def validate(data):
    need(type(data) is dict and set(data)==FIELDS, 'exact cloud executor identity fields')
    need(data['schema']=='CLOUD_EXECUTOR_IDENTITY_V1', 'cloud executor identity schema')
    for name,n in (('source_commit',40),('host_identity_sha256',64)):
        need(type(data[name]) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',data[name]) is not None, 'executor '+name)
    for name in ('execution_id','boot_id'):
        value=data[name]
        need(type(value) is str and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',value) is not None, 'executor '+name)
        need(str(uuid.UUID(value))==value and uuid.UUID(value).int!=0, 'nonzero canonical executor '+name)
    for name in ('controller_pid','start_tick'):
        need(type(data[name]) is int and 0<data[name]<=2**63-1, 'executor '+name)
    started=data['started_monotonic']
    need(type(started) in (int,float) and 0<=started<=2**63-1 and math.isfinite(started), 'executor monotonic start')
    return dict(data)

def verify_owner(data):
    checked=validate(data)
    stat=pathlib.Path('/proc')/str(checked['controller_pid'])/'stat'
    stat=stat.read_text()
    # comm may contain spaces and ')'; fields after its final ')' start at state.
    tail=stat.rsplit(')',1)
    need(len(tail)==2 and len(tail[1].split())>=20, 'current controller stat fields')
    need(int(tail[0].split('(',1)[0].strip())==checked['controller_pid'], 'current controller stat pid')
    need(tail[1].split()[0] not in ('Z','X','x'), 'controller owner is not live')
    need(int(tail[1].split()[19])==checked['start_tick'], 'current controller start tick')
    boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    need(boot==checked['boot_id'], 'current executor boot identity')
    now=time.monotonic()
    need(math.isfinite(now) and checked['started_monotonic']<=now, 'executor start is in the future')
    return checked

def verify_current(data):
    checked=validate(data)
    need(checked['controller_pid']==os.getpid(), 'identity is not current controller')
    return verify_owner(checked)
