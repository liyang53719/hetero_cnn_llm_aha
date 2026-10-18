"""One pinned opaque firtool acquisition plus one strictly bounded member, never execution."""
import argparse,hashlib,io,json,os,stat,sys,types,zipfile
from pathlib import Path, PurePosixPath

ACQUIRER_BYTES=19263
ACQUIRER_SHA='4807fc702edfeb98d7eab9b86e727fe6d0d116ae7230200be7babb5a2c5b9b69'
PLAN_SHA='249e9ad75a8049934b61e980bbcc61068bb1286b5dfdf69975cb803c9f4dea6a'
MEMBER='org.chipsalliance/llvm-firtool/linux-x64/bin/firtool'
ARCHIVE_NAME='llvm-firtool-1.62.1-linux-x64.jar'
ARCHIVE_SHA='63acdcb58ed12d4c1aa0ecdedc6e2425a252e94eefb75df9253c118d7d222039'
BINARY_SHA='7f52d2a3782d09736895f66e7eb0e5cc4b3b1b18aa1ad0d04fca4cd6e42cd2ee'
ARCHIVE_CAP=64*1024*1024
MEMBER_CAP=32*1024*1024
ENTRY_CAP=4096


def need(ok,why):
    if not ok:raise ValueError(why)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def clean(path):
    p=Path(path).absolute()
    need('..' not in p.parts and not any(x.is_symlink() for x in (p,*p.parents)), 'unsafe path')
    return p


def regular_bytes(path,cap,expected_sha=None,expected_size=None):
    path=clean(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        need(stat.S_ISREG(info.st_mode) and 0<=info.st_size<=cap,'regular bounded file required')
        need(expected_size in (None,info.st_size),'fixed source size')
        raw=f.read(cap+1)
        need(len(raw)==info.st_size and len(raw)<=cap,'file changed or exceeded cap')
    need(expected_sha in (None,sha(raw)),'fixed byte identity')
    return raw


def load_acquirer(source):
    source=clean(source)
    raw=regular_bytes(source/'acquire.py',ACQUIRER_BYTES,ACQUIRER_SHA,ACQUIRER_BYTES)
    regular_bytes(source/'plans'/'firtool.json',65536,PLAN_SHA)
    module=types.ModuleType('fixed_firtool_acquirer');module.__file__=str(source/'acquire.py')
    exec(compile(raw,module.__file__,'exec',dont_inherit=True),module.__dict__)
    return module


def member_bytes(raw,archive_sha=ARCHIVE_SHA,binary_sha=BINARY_SHA):
    """Pure byte gate. Only tests supply alternate hashes for tiny synthetic ZIPs."""
    need(type(raw) is bytes and 0<len(raw)<ARCHIVE_CAP,'archive byte cap')
    need(sha(raw)==archive_sha,'archive SHA')
    # Read exactly the same buffer whose SHA was just checked; never reopen it.
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries=z.infolist();need(0<len(entries)<=ENTRY_CAP,'archive member count cap')
        seen=set()
        for info in entries:
            name=info.orig_filename
            need(name==info.filename and '\\' not in name and '\x00' not in name and ':' not in name,'unsafe ZIP name')
            normalized=name[:-1] if name.endswith('/') else name
            path=PurePosixPath(normalized)
            need(normalized and not path.is_absolute() and all(p not in ('','.','..') for p in normalized.split('/')),'ZIP path escape')
            need(name not in seen,'duplicate ZIP member');seen.add(name)
            kind=stat.S_IFMT(info.external_attr>>16)
            need(kind in (0,stat.S_IFREG,stat.S_IFDIR),'nonregular ZIP entry including symlink')
            need(not info.flag_bits&1,'encrypted ZIP entry')
        matches=[x for x in entries if x.filename==MEMBER]
        need(len(matches)==1,'exact allowlist member required')
        info=matches[0]
        need(not info.is_dir() and stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG),'regular member required')
        need(0<info.file_size<=MEMBER_CAP,'member size cap')
        with z.open(info,'r') as stream:
            data=stream.read(MEMBER_CAP+1)
            need(len(data)==info.file_size and len(data)<=MEMBER_CAP and stream.read(1)==b'','member bounded exact EOF')
    need(sha(data)==binary_sha,'member SHA')
    return data


def write_member(output,data):
    output=clean(output);need(not output.exists() and output.parent.is_dir(),'fresh member destination')
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    need(stat.S_IMODE(output.stat().st_mode)==0o600,'member must remain non-executable mode0600')


def run(source,repository,output):
    acq=load_acquirer(source);plan=acq.load_plan('firtool')
    root=acq.checked_output_root(output,repository,must_be_new=True)
    receipt=acq.acquire(plan,root)
    raw=regular_bytes(root/ARCHIVE_NAME,ARCHIVE_CAP-1,ARCHIVE_SHA)
    data=member_bytes(raw)
    binary=root/'firtool';write_member(binary,data)
    regular_bytes(binary,MEMBER_CAP,BINARY_SHA,len(data))
    result={'status':'MEMBER_BYTES_PREPARED_PENDING_OUTER_EXIT0','terminal_success':False,
      'archive_relative_destination':ARCHIVE_NAME,'archive_bytes':len(raw),'archive_sha256':ARCHIVE_SHA,
      'member_name':MEMBER,'binary_relative_destination':'firtool','binary_bytes':len(data),
      'binary_sha256':BINARY_SHA,'binary_mode_octal':'0600','extracted_member_count':1,
      'archive_receipt_sha256':sha(regular_bytes(root/'ACQUISITION.json',65536)),
      'received_bytes':receipt['received_bytes'],'binary_executed':False,'installed':False,
      'rtl_generated':False,'host_executed':False,
      'acceptance_requires':'outer exit0 and elapsed<=180 plus actual acquisition/member identity review'}
    warning=acq.write_json(root/'MEMBER.json',result)
    if warning is not None:result['member_receipt_cleanup_warning']=warning
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('acquisition-source','repository','output-root'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--execute-reviewed-acquisition',action='store_true');a=p.parse_args()
    need(a.execute_reviewed_acquisition,'explicit guard required; parent authorization remains separate')
    print(json.dumps(run(a.acquisition_source,a.repository,a.output_root),sort_keys=True))


if __name__=='__main__':
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode,'use python -I -S -B')
    main()
