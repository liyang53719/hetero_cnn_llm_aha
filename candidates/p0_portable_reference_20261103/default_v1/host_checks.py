"""Linux host observations. ATen DEFAULT is separate from OS CPU flags."""
import hashlib
import json
import os
import platform
from pathlib import Path
import sys
from fixture_gate import need, sha


def available_memory():
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))) * 1024
    # Actual cgroup-v2 remaining allowance, including inherited tighter ancestors.
    cgroups = [line.split(':', 2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::')]
    need(len(cgroups) == 1, 'RESOURCE_ADMISSION')
    rel = Path(cgroups[0].lstrip('/'))
    need('..' not in rel.parts, 'RESOURCE_ADMISSION')
    base = Path('/sys/fs/cgroup')
    current = base / rel
    need(current.is_dir(), 'RESOURCE_ADMISSION')
    remainders = []
    while True:
        maximum = current / 'memory.max'
        usage = current / 'memory.current'
        if maximum.is_file() and usage.is_file():
            cap = maximum.read_text().strip()
            used = int(usage.read_text().strip())
            if cap != 'max':
                remainders.append(max(0, int(cap) - used))
        if current == base:
            break
        current = current.parent
    return min([available] + remainders)


def host_evidence():
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'ABI')
    need(platform.python_implementation() == 'CPython' and sys.version_info[:2] == (3, 12), 'ABI')
    affinity = sorted(os.sched_getaffinity(0))
    need(0 < len(affinity) <= 4096, 'CPU_PROOF')
    processors = {}
    for block in Path('/proc/cpuinfo').read_text().strip().split('\n\n'):
        fields = dict(line.split(':', 1) for line in block.splitlines() if ':' in line)
        fields = {k.strip(): v.strip() for k, v in fields.items()}
        if 'processor' in fields:
            processors[int(fields['processor'])] = fields
    need(set(affinity) <= processors.keys(), 'CPU_PROOF')
    intersection = None
    rows = []
    for cpu in affinity:
        row = processors[cpu]
        need(all(k in row for k in ('vendor_id', 'cpu family', 'model', 'flags')), 'CPU_PROOF')
        flags = set(row['flags'].split())
        intersection = flags if intersection is None else intersection & flags
        rows.append(dict(cpu=cpu, vendor=row['vendor_id'], family=row['cpu family'], model=row['model'], flags=sorted(flags)))
    need('sse2' in intersection, 'CPU_PROOF')
    evidence = dict(architecture=platform.machine(), python_implementation=platform.python_implementation(), python_version=platform.python_version(), python_sha256=sha(Path(sys.executable).resolve()), kernel=platform.release(), libc=list(platform.libc_ver()), affinity=affinity, processors=rows, flags_intersection=sorted(intersection), evidence_source='LINUX_PROC_CPUINFO_NOT_CPUID_EXECUTION', dispatch_domain='DEFAULT_NOT_SCALAR_ONLY', historical_affinity_equality_proven=False)
    stdlib = {}
    for name, module in sorted(sys.modules.copy().items()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and not Path(path).is_relative_to(Path(__file__).resolve().parent):
            stdlib[name] = sha(path)
    evidence['loaded_host_python_module_sha256'] = stdlib
    evidence['stdlib_scope'] = 'LOADED_HOST_MODULES_ONLY_NOT_COMPLETE_OS_CLOSURE'
    digest = hashlib.sha256((json.dumps(evidence, sort_keys=True, separators=(',', ':'))+'\n').encode()).hexdigest()
    return evidence, digest
