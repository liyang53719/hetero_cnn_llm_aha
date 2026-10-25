"""Verbatim reviewed load_library function; no CDLL before function call."""
import ctypes,os
from pathlib import Path
from common import need,sha as digest

def load_library(config,out):
    binary=Path(config['elf']);need(digest(binary)==config['files'][str(binary)]['sha256'],'ELF before load')
    lib=ctypes.CDLL(str(binary));(Path(out)/'MAPS_AFTER_CDLL.txt').write_text(Path('/proc/self/maps').read_text());need(Path(lib._name).resolve()==binary,'CDLL identity')
    class DlInfo(ctypes.Structure):
        _fields_=[('name',ctypes.c_char_p),('base',ctypes.c_void_p),('symbol',ctypes.c_char_p),('address',ctypes.c_void_p)]
    system=ctypes.CDLL(None);system.dladdr.argtypes=[ctypes.c_void_p,ctypes.POINTER(DlInfo)];system.dladdr.restype=ctypes.c_int
    info=DlInfo();need(system.dladdr(ctypes.cast(lib.matrix_normal_step,ctypes.c_void_p),ctypes.byref(info))!=0,'resolved symbol')
    need(Path(os.fsdecode(info.name)).resolve()==binary,'symbol ELF identity')
    st=binary.stat();found=False;math=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        parts=line.split(maxsplit=5)
        if len(parts)!=6:continue
        path=parts[5]
        if path==str(binary):
            need(int(parts[4])==st.st_ino,'mapped ELF inode');found=True
        if path.startswith('/') and Path(path).name.startswith(('libc.so','libm.so','libstdc++','libgcc_s')):
            need(path in config['files'],'unbound math runtime');need(digest(path)==config['files'][path]['sha256'],'math runtime drift');math.append(path)
    need(found and any(Path(p).name.startswith('libm.so') for p in math),'ELF and math mappings')
    return lib,dict(elf_sha256=digest(binary),inode=st.st_ino,device=st.st_dev,math_runtime=sorted(set(math)))
