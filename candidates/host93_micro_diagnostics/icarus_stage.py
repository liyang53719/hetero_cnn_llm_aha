"""SOURCE-only single pinned Ubuntu Icarus package staging component.

Import performs no application I/O. stage() is only for the owner's reviewed,
isolated child: 120 s parent phase, 90 s cooperative work deadline, 512 MiB AS,
4 MiB per-file FSIZE, 16 MiB tree and bounded logs. This module never installs a
package or executes a staged binary. No generic archive extraction is used.
Only the pinned Zstandard member pair is accepted. Decompression uses a
protected pre-existing host libzstd through a checked same-inode descriptor.
"""
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import sys
import time
import urllib.request

SCHEMA = 'PINNED_ICARUS_PRIVATE_STAGE_V1'
PACKAGE_URL = 'https://archive.ubuntu.com/ubuntu/pool/universe/i/iverilog/iverilog_12.0-2build2_amd64.deb'
PACKAGE_FILENAME = 'iverilog_12.0-2build2_amd64.deb'
PACKAGE_BYTES = 2125764
PACKAGE_SHA256 = 'f19394cee05ad526e0eb3873bc6c17a5828f56df17fbe2db40cb66513a2d4667'
IVL_ROOT = 'usr/lib/x86_64-linux-gnu/ivl'
DEADLINE_SECONDS = 90
SOCKET_TIMEOUT_SECONDS = 30
MAX_ADDRESS_SPACE = 512 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_DATA_TAR_BYTES = 16 * 1024 * 1024
MAX_CONTROL_TAR_BYTES = 1024 * 1024
MAX_CONTROL_COMPRESSED_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 32768
MAX_TAR_HEADERS = 256
MAX_TAR_ZERO_TAIL = 10240
MAX_PATH_BYTES = 256
MAX_ZSTD_LIBRARY_BYTES = 4 * 1024 * 1024
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
EXECUTABLE_PATHS = frozenset((
    'usr/bin/iverilog', 'usr/bin/vvp', IVL_ROOT + '/ivl',
    IVL_ROOT + '/ivlpp', IVL_ROOT + '/vhdlpp'))
# Literal names copied from the official noble/amd64 public filelist.
SELECTED_PATHS = (
    'usr/bin/iverilog', 'usr/bin/vvp',
    IVL_ROOT + '/blif-s.conf', IVL_ROOT + '/blif.conf', IVL_ROOT + '/blif.tgt',
    IVL_ROOT + '/cadpli.vpl', IVL_ROOT + '/include/constants.vams',
    IVL_ROOT + '/include/disciplines.vams', IVL_ROOT + '/ivl', IVL_ROOT + '/ivlpp',
    IVL_ROOT + '/null-s.conf', IVL_ROOT + '/null.conf', IVL_ROOT + '/null.tgt',
    IVL_ROOT + '/pcb-s.conf', IVL_ROOT + '/pcb.conf', IVL_ROOT + '/pcb.tgt',
    IVL_ROOT + '/sizer-s.conf', IVL_ROOT + '/sizer.conf', IVL_ROOT + '/sizer.tgt',
    IVL_ROOT + '/stub-s.conf', IVL_ROOT + '/stub.conf', IVL_ROOT + '/stub.tgt',
    IVL_ROOT + '/system.vpi', IVL_ROOT + '/v2005_math.vpi', IVL_ROOT + '/v2009.vpi',
    IVL_ROOT + '/va_math.vpi', IVL_ROOT + '/vhdl-s.conf', IVL_ROOT + '/vhdl.conf',
    IVL_ROOT + '/vhdl.tgt', IVL_ROOT + '/vhdl_sys.vpi', IVL_ROOT + '/vhdl_textio.vpi',
    IVL_ROOT + '/vhdlpp', IVL_ROOT + '/vlog95-s.conf', IVL_ROOT + '/vlog95.conf',
    IVL_ROOT + '/vlog95.tgt', IVL_ROOT + '/vpi_debug.vpi', IVL_ROOT + '/vvp-s.conf',
    IVL_ROOT + '/vvp.conf', IVL_ROOT + '/vvp.tgt')
ALL_DATA_FILES = frozenset(SELECTED_PATHS + (
    'usr/bin/iverilog-vpi',
    'usr/include/iverilog/_pli_types.h', 'usr/include/iverilog/acc_user.h',
    'usr/include/iverilog/ivl_target.h', 'usr/include/iverilog/sv_vpi_user.h',
    'usr/include/iverilog/veriuser.h', 'usr/include/iverilog/vpi_user.h',
    'usr/lib/x86_64-linux-gnu/libveriuser.a', 'usr/lib/x86_64-linux-gnu/libvpi.a',
    'usr/share/doc/iverilog/BUGS.txt.gz', 'usr/share/doc/iverilog/QUICK_START.txt',
    'usr/share/doc/iverilog/attributes.txt', 'usr/share/doc/iverilog/changelog.Debian.gz',
    'usr/share/doc/iverilog/copyright', 'usr/share/doc/iverilog/cygwin.txt',
    'usr/share/doc/iverilog/developer-quick-start.txt.gz',
    'usr/share/doc/iverilog/examples/clbff.v', 'usr/share/doc/iverilog/examples/des.v',
    'usr/share/doc/iverilog/examples/hello.vl', 'usr/share/doc/iverilog/examples/hello_vpi.c',
    'usr/share/doc/iverilog/examples/hello_vpi.vl', 'usr/share/doc/iverilog/examples/outff.v',
    'usr/share/doc/iverilog/examples/pal_reg.v', 'usr/share/doc/iverilog/examples/show_vcd.vl',
    'usr/share/doc/iverilog/examples/sqrt-virtex.v', 'usr/share/doc/iverilog/examples/sqrt.vl',
    'usr/share/doc/iverilog/examples/xnf_add.vl', 'usr/share/doc/iverilog/examples/xram16x1.v',
    'usr/share/doc/iverilog/extensions.txt', 'usr/share/doc/iverilog/glossary.txt',
    'usr/share/doc/iverilog/ieee1364-notes.txt.gz', 'usr/share/doc/iverilog/ivl_target.txt',
    'usr/share/doc/iverilog/lpm.txt', 'usr/share/doc/iverilog/mingw-cross.txt',
    'usr/share/doc/iverilog/mingw.txt', 'usr/share/doc/iverilog/netlist.txt.gz',
    'usr/share/doc/iverilog/swift.txt', 'usr/share/doc/iverilog/t-dll.txt',
    'usr/share/doc/iverilog/va_math.txt', 'usr/share/doc/iverilog/vpi.txt',
    'usr/share/doc/iverilog/xilinx-hint.txt', 'usr/share/man/man1/iverilog-vpi.1.gz',
    'usr/share/man/man1/iverilog.1.gz', 'usr/share/man/man1/vvp.1.gz'))
CONTROL_FILES = frozenset(('control', 'md5sums', 'postinst', 'postrm', 'preinst',
                           'prerm', 'triggers', 'conffiles'))

AR_PINS = (('debian-binary', 4, 'd526eb4e878a23ef26ae190031b4efd2d58ed66789ac049ea3dbaf74c9df7402'), ('control.tar.zst', 2881, '8a41e241b984bd48d81c7de952a932ea037e7df1877ea367d99278330e632917'), ('data.tar.zst', 2122690, '60583389fb0eba7a4b9407c850624648e22ea80f3e85d50e1e4f25deaaa57f45'))
TAR_PINS = {'control.tar.zst': (10240, 'aeac2541904d12b884d3b263948dc6b5e05593d712fbb9705b56403810fd631e'), 'data.tar.zst': (6840320, 'd520b7e4086b27bc55b984dd3ca73f7a58bbe2f310c877ad67c3e11eadf0fe01')}
SELECTED_PINS = {'usr/bin/iverilog': (51640, 'a6071e4b4a68feafca0c8ee0e6aa275eee9a43a108c62801cfd1eca6eab6d8a3'), 'usr/bin/vvp': (1354376, 'a10bd7d4a0850308ac8c2c98115b6a3084f9be978307610f2a521190c28f4023'), 'usr/lib/x86_64-linux-gnu/ivl/blif-s.conf': (96, '3ce285013d51a0f632be229a513c17d4f8a314319c0e7d7fbbe53a2339580e1c'), 'usr/lib/x86_64-linux-gnu/ivl/blif.conf': (96, '3ce285013d51a0f632be229a513c17d4f8a314319c0e7d7fbbe53a2339580e1c'), 'usr/lib/x86_64-linux-gnu/ivl/blif.tgt': (51440, 'd0cbf2e24666d55aff2ee988ad3347db38c3270d362b45ca8e9217948e73adfe'), 'usr/lib/x86_64-linux-gnu/ivl/cadpli.vpl': (51368, '865029a77188db6f3518fb34791f6edcbfc6ea62c508fb0bac95f1847220680e'), 'usr/lib/x86_64-linux-gnu/ivl/include/constants.vams': (1377, '48cb40767dd73f50a3288c0b8b5fc779a6462b4e27f565dd9aae31a53f4a6f09'), 'usr/lib/x86_64-linux-gnu/ivl/include/disciplines.vams': (1125, '6540e1f3f01b64eee3a26239c1bab6fe80db5b1fca30e336fe40189b52add231'), 'usr/lib/x86_64-linux-gnu/ivl/ivl': (2873976, '85568f74fc0cf8dd3811628203621a0cfddb59d2f6f51c1371465ecdc1282b16'), 'usr/lib/x86_64-linux-gnu/ivl/ivlpp': (68032, 'c6f1072b825e30dd79267e7056f57447f2aea8655f6e24e1e3eb243e988aa4f1'), 'usr/lib/x86_64-linux-gnu/ivl/null-s.conf': (65, '8a4b79342b5d58fcd576238e928403c986bf623e5e9c63fc7e199f5c5bf57fae'), 'usr/lib/x86_64-linux-gnu/ivl/null.conf': (18, '313ef43d707cf69cabac9b02c1cee5223b7179007aa627c0963a567691751cd0'), 'usr/lib/x86_64-linux-gnu/ivl/null.tgt': (14480, 'e2d656691ccd392c46e92cc856a16da611fc3907541b0e89a7d8dd7717f262d5'), 'usr/lib/x86_64-linux-gnu/ivl/pcb-s.conf': (95, '2f184346cab431bfa26ef1bf0a906a8d78469aae495f93974896ec952dee3657'), 'usr/lib/x86_64-linux-gnu/ivl/pcb.conf': (48, '5a84492e9e830658590cc28d5c39d8b137124ac2f6e5c111a838d91b99aa3cb9'), 'usr/lib/x86_64-linux-gnu/ivl/pcb.tgt': (63816, '97f1983b021e61e7404c4cca31b4a74f65d217a450a0404950620ec26db3c197'), 'usr/lib/x86_64-linux-gnu/ivl/sizer-s.conf': (97, '03a8f24468995e87b23840915b613abd339843a6ec6d0931b57ea56720ff415d'), 'usr/lib/x86_64-linux-gnu/ivl/sizer.conf': (97, '03a8f24468995e87b23840915b613abd339843a6ec6d0931b57ea56720ff415d'), 'usr/lib/x86_64-linux-gnu/ivl/sizer.tgt': (26864, '535a22b1527d979fa8af7e2d814ebccfd89ab1908ac7edde964993a568b4aa5b'), 'usr/lib/x86_64-linux-gnu/ivl/stub-s.conf': (96, 'ca77cff51d74ad77e33efd589c82fb410823ad88a5933a5e4aca86251250b302'), 'usr/lib/x86_64-linux-gnu/ivl/stub.conf': (49, '03c9241decbe4502f087790fe7eaf6568fb7992788fbf56be0f69737a98c67fb'), 'usr/lib/x86_64-linux-gnu/ivl/stub.tgt': (84192, '9813d335364d8bac054782a2c4b69f898715325bd9153cb1dfb4d4c305c325c3'), 'usr/lib/x86_64-linux-gnu/ivl/system.vpi': (436976, '6868f58ea8946117f02081ba8d5de3ad2faa4282268f1338c6a00cbe9743aa60'), 'usr/lib/x86_64-linux-gnu/ivl/v2005_math.vpi': (23096, '262ae7cb39f33e902a20f38c8b09485e59de2bfa95df2318b8a50e6b304bb80c'), 'usr/lib/x86_64-linux-gnu/ivl/v2009.vpi': (39120, '70b346009b85cd201efb4c39e4160af31dd382ada1d3377ad4f4e751c5164dbf'), 'usr/lib/x86_64-linux-gnu/ivl/va_math.vpi': (14600, '6778d7fce72f28a66f58574de8c5349e4a6db9870957abcca4ae47624b3039e6'), 'usr/lib/x86_64-linux-gnu/ivl/vhdl-s.conf': (103, 'd9b3d7de12e25e14c86738110f4e2baf3711f60a161e34ad329104f13ccabc5d'), 'usr/lib/x86_64-linux-gnu/ivl/vhdl.conf': (86, '7f8563bd0a386bedf111f5f23ce827b8efd6749cb3b104cf236358324ccd840a'), 'usr/lib/x86_64-linux-gnu/ivl/vhdl.tgt': (289880, 'fb410b5516953774dd7235fbb8e619706c997a078735582b4e328902dacc6dfb'), 'usr/lib/x86_64-linux-gnu/ivl/vhdl_sys.vpi': (22776, '0704b9c10be2a9a07990fd1d319d0758329157061c2fad1bc6fe2ff093fcd659'), 'usr/lib/x86_64-linux-gnu/ivl/vhdl_textio.vpi': (34984, '51e22882b916f835c9666e0f0e736e09b9888671d159d6bbddfae49d7815a34f'), 'usr/lib/x86_64-linux-gnu/ivl/vhdlpp': (502240, '53241cae469ab7b6007d0ca337be73458b7f974e008cab0e70950912fc460b52'), 'usr/lib/x86_64-linux-gnu/ivl/vlog95-s.conf': (141, 'f4f09237dc90f1e4e58658b2bb14bb446e93619c911b8ead10cc0240f64cad51'), 'usr/lib/x86_64-linux-gnu/ivl/vlog95.conf': (57, '47d4a923819bdf601c5fa62065b6787f81d2ea64cb0e6b33c33c4e9001d356c0'), 'usr/lib/x86_64-linux-gnu/ivl/vlog95.tgt': (166040, 'd38913f8714e95d816715d3558386c40ec1e325e681c759ed96a17099bfecabd'), 'usr/lib/x86_64-linux-gnu/ivl/vpi_debug.vpi': (14504, 'c867c851e5d38c737ba584b5fad1aad018efc453e38c575571f6ae47cd080049'), 'usr/lib/x86_64-linux-gnu/ivl/vvp-s.conf': (128, '34cc3cf237ec8a86b3b740dd656a6953bbe3ff681da0dd0c7dde004c2d98dd84'), 'usr/lib/x86_64-linux-gnu/ivl/vvp.conf': (81, '6013ffb100e35d3a4656d3a24836be36bb782957c174e527c1c570ffe7aa5b41'), 'usr/lib/x86_64-linux-gnu/ivl/vvp.tgt': (190808, 'b8bc79e5fcaaa1b80c61b18823b16e766e636675ea6b8dc0f59e5d3bf7eabc93')}

class AcquisitionError(ValueError):
    """Errors carry only developer-authored fixed labels, never raw tool text."""


def require(ok, reason):
    if not ok:
        raise AcquisitionError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _remaining(deadline):
    value = deadline - time.monotonic()
    require(value > 0, 'acquisition_deadline')
    return value


def _runtime_contract():
    require(sys.flags.isolated and sys.flags.ignore_environment and sys.flags.no_site
            and sys.flags.no_user_site and sys.flags.dont_write_bytecode,
            'isolated_runtime_required')
    for kind, cap in ((resource.RLIMIT_AS, MAX_ADDRESS_SPACE),
                      (resource.RLIMIT_FSIZE, MAX_FILE_BYTES)):
        soft, hard = resource.getrlimit(kind)
        require(0 < soft <= cap and 0 < hard <= cap, 'resource_limits_required')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AcquisitionError('redirect_refused')

    def http_error_302(self, req, fp, code, msg, headers):
        raise AcquisitionError('redirect_refused')

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _download(deadline):
    try:
        # Platform proxy and certificate-verification defaults only.
        opener = urllib.request.build_opener(_NoRedirect())
        request = urllib.request.Request(PACKAGE_URL, headers={'Accept-Encoding': 'identity'}, method='GET')
        with opener.open(request, timeout=min(SOCKET_TIMEOUT_SECONDS, _remaining(deadline))) as response:
            _remaining(deadline)
            require(response.getcode() == 200, 'http_status_refused')
            require(response.geturl() == PACKAGE_URL, 'response_url_refused')
            lengths = response.headers.get_all('Content-Length', [])
            encodings = response.headers.get_all('Content-Encoding', [])
            require(len(lengths) <= 1, 'content_length_refused')
            if lengths:
                value = lengths[0].strip()
                require(value.isascii() and value.isdecimal() and len(value) <= 12
                        and int(value) == PACKAGE_BYTES, 'content_length_refused')
            require(not encodings or (len(encodings) == 1 and encodings[0].strip().lower() == 'identity'),
                    'content_encoding_refused')
            chunks, count = [], 0
            while count <= PACKAGE_BYTES:
                _remaining(deadline)
                requested = min(16384, PACKAGE_BYTES + 1 - count)
                chunk = response.read(requested)
                _remaining(deadline)
                require(type(chunk) is bytes and len(chunk) <= requested, 'response_body_refused')
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                require(count <= PACKAGE_BYTES, 'package_size_exceeded')
            raw = b''.join(chunks)
            require(len(raw) == PACKAGE_BYTES and sha(raw) == PACKAGE_SHA256, 'package_identity')
            return raw
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('transport_failed') from None


def _ar_entries(raw):
    require(raw.startswith(b'!<arch>\n'), 'ar_magic')
    entries = {}
    pos = 8
    for ordinal in range(3):
        require(pos + 60 <= len(raw), 'ar_header_truncated')
        h = raw[pos:pos + 60]
        require(h[58:] == b'`\n', 'ar_header_marker')
        name_raw = h[:16].rstrip(b' ')
        expected_name, expected_size, expected_digest = AR_PINS[ordinal]
        require(name_raw == expected_name.encode('ascii'), 'ar_name_or_order')
        for field in (h[16:28], h[28:34], h[34:40], h[48:58]):
            require(re.fullmatch(b'[0-9]+ *', field) is not None, 'ar_decimal_field')
        require(re.fullmatch(b'[0-7]+ *', h[40:48]) is not None, 'ar_mode_field')
        size = int(h[48:58])
        cap = (4, MAX_CONTROL_COMPRESSED_BYTES, PACKAGE_BYTES)[ordinal]
        require(0 < size <= cap and size == expected_size, 'ar_member_bound')
        start, end = pos + 60, pos + 60 + size
        require(end <= len(raw), 'ar_member_truncated')
        name = name_raw.decode('ascii')
        entries[name] = raw[start:end]
        require(sha(entries[name]) == expected_digest, 'ar_member_identity')
        pos = end
        if size % 2:
            require(raw[pos:pos + 1] == b'\n', 'ar_padding')
            pos += 1
    require(pos == len(raw), 'ar_trailing_or_extra_member')
    require(entries['debian-binary'] == b'2.0\n', 'debian_version')
    return entries


@contextlib.contextmanager
def _zstd_library():
    """Only a protected system libzstd; no install, environment path or fallback."""
    directory = file_fd = None
    try:
        directory = os.open('/', DIRECTORY_FLAGS)
        for component in ('usr', 'lib', 'x86_64-linux-gnu'):
            child = os.open(component, DIRECTORY_FLAGS, dir_fd=directory)
            os.close(directory)
            directory = child
            st = os.fstat(directory)
            require(st.st_uid == 0 and not (st.st_mode & 0o022), 'zstd_directory_untrusted')
        name = 'libzstd.so.1'
        link = os.stat(name, dir_fd=directory, follow_symlinks=False)
        require(link.st_uid == 0, 'zstd_owner_refused')
        if stat.S_ISLNK(link.st_mode):
            target = os.readlink(name, dir_fd=directory)
            require(type(target) is str and len(target) <= 64 and
                    re.fullmatch(r'libzstd\.so\.1\.[0-9]{1,3}\.[0-9]{1,3}', target),
                    'zstd_symlink_refused')
            require(_inode(os.stat(name, dir_fd=directory, follow_symlinks=False)) == _inode(link),
                    'zstd_symlink_changed')
            name = target
        file_fd = os.open(name, READ_FLAGS, dir_fd=directory)
        before = os.fstat(file_fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and not (before.st_mode & 0o022) and before.st_nlink >= 1
                and 0 < before.st_size <= MAX_ZSTD_LIBRARY_BYTES, 'zstd_library_inode')
        count, hasher = 0, hashlib.sha256()
        while count <= before.st_size:
            block = os.read(file_fd, min(65536, before.st_size + 1 - count))
            if not block:
                break
            count += len(block)
            hasher.update(block)
        require(count == before.st_size and _inode(os.fstat(file_fd)) == _inode(before)
                and _inode(os.stat(name, dir_fd=directory, follow_symlinks=False)) == _inode(before),
                'zstd_library_changed')
        # /proc/self/fd selects the exact already-open and hashed inode.
        try:
            library = ctypes.CDLL('/proc/self/fd/' + str(file_fd), mode=ctypes.RTLD_LOCAL)
        except Exception:
            raise AcquisitionError('zstd_library_load_failed') from None
        require(all(hasattr(library, symbol) for symbol in
                ('ZSTD_findFrameCompressedSize', 'ZSTD_decompress', 'ZSTD_isError')),
                'zstd_symbols_unavailable')
        library.ZSTD_findFrameCompressedSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_findFrameCompressedSize.restype = ctypes.c_size_t
        library.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_decompress.restype = ctypes.c_size_t
        library.ZSTD_isError.argtypes = [ctypes.c_size_t]
        library.ZSTD_isError.restype = ctypes.c_uint
        identity = {'kind': 'existing_host_libzstd_same_inode',
                    'basename': name, 'bytes': count, 'sha256': hasher.hexdigest(),
                    'device': before.st_dev, 'inode': before.st_ino}
        require(_inode(os.fstat(file_fd)) == _inode(before), 'zstd_library_changed')
        yield library, identity
        os.lseek(file_fd, 0, os.SEEK_SET)
        after_hasher, after_count = hashlib.sha256(), 0
        while after_count <= before.st_size:
            block = os.read(file_fd, min(65536, before.st_size + 1 - after_count))
            if not block:
                break
            after_count += len(block)
            after_hasher.update(block)
        require(after_count == count and after_hasher.hexdigest() == identity['sha256'],
                'zstd_library_changed')
        require(_inode(os.fstat(file_fd)) == _inode(before) and
                _inode(os.stat(name, dir_fd=directory, follow_symlinks=False)) == _inode(before),
                'zstd_library_changed')
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('zstd_decoder_unavailable') from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory is not None:
            os.close(directory)


def _expand(raw, name, cap):
    try:
        require(name in TAR_PINS and name.endswith('.zst'), 'compression_refused')
        expected_size, expected_digest = TAR_PINS[name]
        require(type(raw) is bytes and 0 < len(raw) <= PACKAGE_BYTES
                and raw.startswith(b'\x28\xb5\x2f\xfd'), 'zstd_input_refused')
        require(1024 <= expected_size <= cap and expected_size % 512 == 0, 'decompression_bound')
        with _zstd_library() as (decoder, identity):
            source = ctypes.create_string_buffer(raw, len(raw))
            framed = decoder.ZSTD_findFrameCompressedSize(source, len(raw))
            require(not decoder.ZSTD_isError(framed) and framed == len(raw), 'compressed_stream_framing')
            # Only the exact independently pinned output allocation is allowed.
            destination = ctypes.create_string_buffer(expected_size)
            size = decoder.ZSTD_decompress(destination, expected_size, source, len(raw))
            require(not decoder.ZSTD_isError(size) and size == expected_size, 'decompression_bound')
            expanded = destination.raw
            require(len(expanded) == expected_size and sha(expanded) == expected_digest,
                    'expanded_tar_identity')
        return expanded, identity
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('decompression_failed') from None


def _text(raw):
    value, sep, tail = raw.partition(b'\0')
    require(not sep or not any(tail), 'tar_text_tail')
    require(all(32 <= c < 127 for c in value), 'tar_text_encoding')
    return value.decode('ascii')


def _octal(raw, empty=False):
    require(not raw[0] & 128, 'tar_base256_refused')
    value = raw.rstrip(b'\0 ').lstrip(b' ')
    require((empty and not value) or re.fullmatch(b'[0-7]+', value), 'tar_octal_encoding')
    return int(value or b'0', 8)


def _ancestors(paths):
    result = {'.'}
    for path in paths:
        pieces = path.split('/')
        for i in range(1, len(pieces)):
            result.add('/'.join(pieces[:i]))
    return result


def _tar_path(name, kind):
    require(name.startswith('./'), 'tar_relative_prefix')
    path = name[2:]
    if kind == b'5':
        path = path[:-1] if path.endswith('/') else path
        if not path:
            return '.'
    require(0 < len(path) <= MAX_PATH_BYTES and not path.startswith('/')
            and all(32 < ord(c) < 127 and c not in '\\:' for c in path), 'tar_path_syntax')
    require(all(p not in ('', '.', '..') for p in path.split('/')), 'tar_path_components')
    return path


def _parse_tar(raw, allowed_files, *, complete):
    allowed_dirs = _ancestors(allowed_files)
    pos, seen, files, metadata = 0, set(), {}, {}
    while pos + 512 <= len(raw):
        h = raw[pos:pos + 512]
        if not any(h):
            tail = raw[pos:]
            require(1024 <= len(tail) <= MAX_TAR_ZERO_TAIL and not any(tail), 'tar_terminator')
            break
        require(len(seen) < MAX_TAR_HEADERS, 'tar_header_bound')
        require(h[257:265] in (b'ustar  \0', b'ustar\x0000'), 'tar_magic_version')
        require(not any(h[345:512]), 'tar_extension_fields_refused')
        require(_octal(h[148:156]) == sum(h[:148]) + 256 + sum(h[156:]), 'tar_checksum')
        kind = h[156:157]
        require(kind in (b'0', b'5'), 'tar_type_refused')
        mode = _octal(h[100:108])
        require(mode in (0o644, 0o755), 'tar_mode_refused')
        for field in (h[108:116], h[116:124], h[136:148]):
            _octal(field)
        require(_octal(h[329:337], True) == 0 and _octal(h[337:345], True) == 0,
                'tar_device_refused')
        _text(h[265:297]); _text(h[297:329])
        require(not _text(h[157:257]), 'tar_link_refused')
        path = _tar_path(_text(h[:100]), kind)
        require(path not in seen, 'tar_duplicate_path')
        seen.add(path)
        size = _octal(h[124:136])
        require(0 <= size <= MAX_FILE_BYTES, 'tar_member_bound')
        require((kind == b'5' and path in allowed_dirs and size == 0 and mode == 0o755)
                or (kind == b'0' and path in allowed_files), 'tar_inventory_refused')
        start, end = pos + 512, pos + 512 + size
        padded = start + ((size + 511) // 512) * 512
        require(padded <= len(raw), 'tar_member_truncated')
        require(not any(raw[end:padded]), 'tar_member_padding')
        if kind == b'0':
            files[path] = raw[start:end]
            metadata[path] = {'bytes': size, 'archive_mode': oct(mode), 'sha256': sha(files[path])}
        pos = padded
    else:
        raise AcquisitionError('tar_missing_terminator')
    require(not complete or set(files) == set(allowed_files), 'tar_file_inventory')
    return files, metadata


def _control_identity(raw):
    require(len(raw) <= 65536, 'control_file_bound')
    try:
        text = raw.decode('utf-8', 'strict')
        fields, current = {}, None
        for line in text.splitlines():
            if line.startswith((' ', '\t')):
                require(current is not None, 'control_orphan_continuation')
                fields[current] += '\n' + line
            elif line:
                key, sep, value = line.partition(':')
                require(sep and re.fullmatch('[A-Za-z0-9-]+', key) and key not in fields,
                        'control_fields_refused')
                fields[key], current = value.strip(), key
            else:
                current = None
        require({k: fields.get(k) for k in ('Package', 'Version', 'Architecture')} ==
                {'Package': 'iverilog', 'Version': '12.0-2build2', 'Architecture': 'amd64'},
                'control_identity')
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('control_parse_failed') from None


def validate_package(raw):
    """Pure fixed-package validation. Exact whole buffer is hashed before parsing."""
    try:
        require(type(raw) is bytes and len(raw) == PACKAGE_BYTES and sha(raw) == PACKAGE_SHA256,
                'package_identity')
        entries = _ar_entries(raw)
        control_name = next(n for n in entries if n.startswith('control.'))
        data_name = next(n for n in entries if n.startswith('data.'))
        control_tar, decoder_identity = _expand(entries[control_name], control_name, MAX_CONTROL_TAR_BYTES)
        controls, _ = _parse_tar(control_tar, CONTROL_FILES, complete=False)
        require('control' in controls, 'control_missing')
        _control_identity(controls['control'])
        data_tar, second_decoder = _expand(entries[data_name], data_name, MAX_DATA_TAR_BYTES)
        require(second_decoder == decoder_identity, 'zstd_decoder_changed')
        files, metadata = _parse_tar(data_tar, ALL_DATA_FILES, complete=True)
        selected = {p: files[p] for p in SELECTED_PATHS}
        require({p: (len(body), sha(body)) for p, body in selected.items()} == SELECTED_PINS,
                'selected_member_identity')
        require(set(EXECUTABLE_PATHS) <= set(selected), 'executable_inventory')
        for path in EXECUTABLE_PATHS:
            require(metadata[path]['archive_mode'] == '0o755', 'executable_archive_mode')
        require(sum(len(v) for v in selected.values()) + MAX_RECEIPT_BYTES <= MAX_OUTPUT_BYTES,
                'output_tree_bound')
        receipt = {'schema': SCHEMA, 'host_decoder': decoder_identity, 'package': {'filename': PACKAGE_FILENAME,
                   'bytes': PACKAGE_BYTES, 'sha256': PACKAGE_SHA256},
                   'control_tar_sha256': sha(control_tar), 'data_tar_sha256': sha(data_tar),
                   'selected': [{'path': p, **metadata[p],
                                 'staged_mode': '0o700' if p in EXECUTABLE_PATHS else '0o600'}
                                for p in SELECTED_PATHS],
                   'dynamic_libraries_installed': False, 'executables_invoked': False,
                   'runtime_qualified': False}
        return selected, receipt
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('package_parse_failed') from None


def _open_parent(destination, *, absent=True):
    require(isinstance(destination, Path) and destination.is_absolute(), 'destination_absolute_required')
    parts = destination.parts
    require(len(parts) >= 3 and len(str(destination)) <= 4096
            and all(p not in ('', '.', '..') and '\x00' not in p for p in parts[1:]),
            'destination_syntax')
    fd = os.open('/', DIRECTORY_FLAGS)
    try:
        for part in parts[1:-1]:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        st = os.fstat(fd)
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                and stat.S_IMODE(st.st_mode) == 0o700, 'destination_parent_not_private')
        if absent:
            try:
                os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise AcquisitionError('destination_exists')
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def _inode(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_mode, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def _write_at(fd, name, raw, mode):
    require('/' not in name and name not in ('', '.', '..') and mode in (0o600, 0o700),
            'output_filename_or_mode')
    require(type(raw) is bytes and len(raw) <= MAX_FILE_BYTES, 'output_file_bound')
    child = os.open(name, WRITE_FLAGS, 0o600, dir_fd=fd)
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(child, raw[offset:])
            require(written > 0, 'output_short_write')
            offset += written
        os.fchmod(child, mode)
        os.fsync(child)
        st = os.fstat(child)
        require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and st.st_nlink == 1
                and stat.S_IMODE(st.st_mode) == mode and st.st_size == len(raw), 'output_inode')
    finally:
        os.close(child)
    child = os.open(name, READ_FLAGS, dir_fd=fd)
    try:
        require(_inode(os.fstat(child)) == _inode(st), 'output_replaced')
        chunks, count = [], 0
        while count <= len(raw):
            block = os.read(child, min(65536, len(raw) + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
        require(b''.join(chunks) == raw, 'output_readback')
        require(_inode(os.fstat(child)) == _inode(st)
                and _inode(os.stat(name, dir_fd=fd, follow_symlinks=False)) == _inode(st),
                'output_changed')
    finally:
        os.close(child)


def stage(destination: Path) -> dict:
    """Stage 39 fixed files beneath an absent leaf of a private owned 0700 parent.

    Returns and writes a safe receipt containing only package/member identities,
    fixed relative names, fixed flags and modes. The caller owns partial-output
    cleanup on failure. No archive paths are used to choose output destinations.
    """
    parent_fd = root_fd = None
    dirs = {}
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        _runtime_contract()
        parent_fd, leaf = _open_parent(destination)
        # Required capability preflight before any network request.
        with _zstd_library() as (_decoder, preflight_decoder):
            pass
        _remaining(deadline)
        raw = _download(deadline)
        selected, receipt = validate_package(raw)
        require(receipt['host_decoder'] == preflight_decoder, 'zstd_decoder_changed')
        _remaining(deadline)
        receipt_raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode('ascii')
        require(len(receipt_raw) <= MAX_RECEIPT_BYTES, 'receipt_bound')
        # Nothing is created until complete download, same-buffer identity,
        # control identity, archive validation and the selected inventory pass.
        os.mkdir(leaf, 0o700, dir_fd=parent_fd)
        root_fd = os.open(leaf, DIRECTORY_FLAGS, dir_fd=parent_fd)
        dirs['.'] = root_fd
        for path in sorted(_ancestors(SELECTED_PATHS) - {'.'}, key=lambda p: (p.count('/'), p)):
            parent, _, name = path.rpartition('/')
            fd = dirs[parent or '.']
            os.mkdir(name, 0o700, dir_fd=fd)
            dirs[path] = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
        for fd in dirs.values():
            st = os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o700
                    and st.st_uid == os.geteuid(), 'output_directory_mode')
        for path in SELECTED_PATHS:
            _remaining(deadline)
            parent, _, name = path.rpartition('/')
            _write_at(dirs[parent], name, selected[path], 0o700 if path in EXECUTABLE_PATHS else 0o600)
        _write_at(root_fd, 'RECEIPT.json', receipt_raw, 0o600)
        expected = {p: set() for p in dirs}
        for path in (set(dirs) - {'.'}) | set(SELECTED_PATHS) | {'RECEIPT.json'}:
            parent, _, name = path.rpartition('/')
            expected[parent or '.'].add(name)
        for path, fd in dirs.items():
            require(set(os.listdir(fd)) == expected[path], 'output_inventory')
            os.fsync(fd)
        os.fsync(parent_fd)
        _remaining(deadline)
        return receipt
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('acquisition_failed') from None
    finally:
        for fd in reversed(list(dirs.values())):
            os.close(fd)
        if parent_fd is not None:
            os.close(parent_fd)


def _checked_receipt(receipt):
    require(type(receipt) is dict and set(receipt) == {'schema', 'package', 'host_decoder',
            'control_tar_sha256', 'data_tar_sha256', 'selected', 'dynamic_libraries_installed',
            'executables_invoked', 'runtime_qualified'}, 'receipt_shape')
    require(receipt['schema'] == SCHEMA and receipt['package'] == {
            'filename': PACKAGE_FILENAME, 'bytes': PACKAGE_BYTES, 'sha256': PACKAGE_SHA256},
            'receipt_package_identity')
    require(all(receipt[k] is False for k in ('dynamic_libraries_installed',
            'executables_invoked', 'runtime_qualified')), 'receipt_staging_flags')
    for k in ('control_tar_sha256', 'data_tar_sha256'):
        require(type(receipt[k]) is str and re.fullmatch('[0-9a-f]{64}', receipt[k]), 'receipt_digest')
    decoder = receipt['host_decoder']
    require(type(decoder) is dict and set(decoder) == {'kind', 'basename', 'bytes', 'sha256', 'device', 'inode'}
            and decoder['kind'] == 'existing_host_libzstd_same_inode', 'receipt_decoder_shape')
    require(type(decoder['basename']) is str and re.fullmatch(r'libzstd\.so\.1(?:\.[0-9]{1,3}\.[0-9]{1,3})?', decoder['basename'])
            and type(decoder['sha256']) is str and re.fullmatch('[0-9a-f]{64}', decoder['sha256'])
            and type(decoder['bytes']) is int and 0 < decoder['bytes'] <= MAX_ZSTD_LIBRARY_BYTES
            and type(decoder['device']) is int and decoder['device'] >= 0
            and type(decoder['inode']) is int and decoder['inode'] > 0, 'receipt_decoder_identity')
    rows = receipt['selected']
    require(type(rows) is list and len(rows) == len(SELECTED_PATHS), 'receipt_inventory')
    total = 0
    for row, path in zip(rows, SELECTED_PATHS):
        require(type(row) is dict and set(row) == {'path', 'bytes', 'archive_mode',
                'sha256', 'staged_mode'} and row['path'] == path, 'receipt_member_shape')
        require(type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_FILE_BYTES,
                'receipt_member_bound')
        require(type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']),
                'receipt_member_digest')
        require(row['archive_mode'] in ('0o644', '0o755') and
                (path not in EXECUTABLE_PATHS or row['archive_mode'] == '0o755') and
                row['staged_mode'] == ('0o700' if path in EXECUTABLE_PATHS else '0o600'),
                'receipt_member_mode')
        require((row['bytes'], row['sha256']) == SELECTED_PINS[path], 'receipt_selected_identity')
        total += row['bytes']
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode('ascii')
    require(len(raw) <= MAX_RECEIPT_BYTES and total + len(raw) <= MAX_OUTPUT_BYTES, 'receipt_bound')
    return raw


def _verify_file_at(parent, name, size, digest, mode):
    child = os.open(name, READ_FLAGS, dir_fd=parent)
    try:
        before = os.fstat(child)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == mode
                and before.st_size == size, 'verified_file_inode')
        hasher, count = hashlib.sha256(), 0
        while count <= size:
            raw = os.read(child, min(65536, size + 1 - count))
            if not raw:
                break
            count += len(raw)
            hasher.update(raw)
        require(count == size and hasher.hexdigest() == digest, 'verified_file_identity')
        require(_inode(os.fstat(child)) == _inode(before) and
                _inode(os.stat(name, dir_fd=parent, follow_symlinks=False)) == _inode(before),
                'verified_file_changed')
    finally:
        os.close(child)


def verify_stage(destination: Path, expected_receipt: dict) -> dict:
    """Read-only revalidation against the TRUSTED stage return, before/after tools.

    The caller must retain the successful stage() receipt before executing any
    staged tool, or supply independently pinned equivalent metadata. Never pass
    an untrusted on-disk RECEIPT as expected_receipt: self-consistent replacement
    would otherwise evade verification. This function does not qualify runtime.
    """
    parent_fd = None
    dirs, identities = {}, {}
    try:
        receipt_raw = _checked_receipt(expected_receipt)
        parent_fd, leaf = _open_parent(destination, absent=False)
        dirs['.'] = os.open(leaf, DIRECTORY_FLAGS, dir_fd=parent_fd)
        for path in sorted(_ancestors(SELECTED_PATHS) - {'.'}, key=lambda p: (p.count('/'), p)):
            parent, _, name = path.rpartition('/')
            dirs[path] = os.open(name, DIRECTORY_FLAGS, dir_fd=dirs[parent or '.'])
        for path, fd in dirs.items():
            st = os.fstat(fd)
            require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                    and stat.S_IMODE(st.st_mode) == 0o700, 'verified_directory_inode')
            identities[path] = _inode(st)
        for row in expected_receipt['selected']:
            parent, _, name = row['path'].rpartition('/')
            _verify_file_at(dirs[parent], name, row['bytes'], row['sha256'], int(row['staged_mode'], 8))
        _verify_file_at(dirs['.'], 'RECEIPT.json', len(receipt_raw), sha(receipt_raw), 0o600)
        expected = {p: set() for p in dirs}
        for path in (set(dirs) - {'.'}) | set(SELECTED_PATHS) | {'RECEIPT.json'}:
            parent, _, name = path.rpartition('/')
            expected[parent or '.'].add(name)
        for path, fd in dirs.items():
            require(set(os.listdir(fd)) == expected[path], 'verified_inventory')
            parent, _, name = path.rpartition('/')
            outer = parent_fd if path == '.' else dirs[parent or '.']
            leafname = leaf if path == '.' else name
            require(_inode(os.fstat(fd)) == identities[path] and
                    _inode(os.stat(leafname, dir_fd=outer, follow_symlinks=False)) == identities[path],
                    'verified_directory_changed')
        return expected_receipt
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError('stage_verification_failed') from None
    finally:
        for fd in reversed(list(dirs.values())):
            os.close(fd)
        if parent_fd is not None:
            os.close(parent_fd)
