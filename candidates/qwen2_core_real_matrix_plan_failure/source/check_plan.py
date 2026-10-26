"""Bounded fixed Verilator 5.032 CMake-hierarchy plan contract, never executes it."""
import hashlib
import os
import re
import stat

ORIGINAL = 'qwen2_matrix_command_endpoint_seed_disabled_impl'
TOP = 'OrderedQkRealMatrixCore'
IDENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]{0,255}\Z')
PATH = re.compile(r'/[A-Za-z0-9_./+-]+\Z')
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
MAX_LINE = 65536
MAX_LINES = 10000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sig(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def path_ok(s):
    require(isinstance(s, str) and PATH.fullmatch(s) and '/..' not in s and '/./' not in s and '//' not in s, 'unsafe fixed path')
    return s


def tokens(s):
    """Only emitted double quoted or plain tokens, with backslash quote escapes."""
    result = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        quoted = s[i] == '"'
        if quoted:
            i += 1
        word = ''
        while i < len(s):
            c = s[i]
            if quoted and c == '"':
                i += 1
                require(i == len(s) or s[i].isspace(), 'joined quoted tokens')
                break
            if not quoted and c.isspace():
                break
            if c == '\\':
                i += 1
                require(i < len(s) and s[i] in "'\\\"", 'unsupported argument escape')
                c = s[i]
            elif not quoted:
                require(c != '"', 'quote inside bare token')
            word += c
            i += 1
        else:
            require(not quoted, 'unterminated quoted token')
        require(word != '', 'empty emitted token')
        result.append(word)
    return result


def forwarded(line_args, source_paths, for_top):
    """Literal V3Options.cpp:415-456,550-565 subset used by this fixed argv."""
    result = []
    skip = False
    skip_number = False
    takes = {'Mdir','clk','lib-create','f','F','v','l2-name','mod-prefix','prefix','protect-lib','protect-key','threads','top-module'}
    for arg in line_args:
        require(isinstance(arg, str) and arg, 'empty argv')
        if skip:
            skip = False
            continue
        if skip_number:
            skip_number = False
            if arg[0].isdigit():
                continue
        opt = arg[2:] if arg.startswith('--') else arg[1:] if arg.startswith('-') else None
        if opt == 'j':
            skip_number = True
        elif opt in takes:
            skip = True
        elif opt == 'build' or (not for_top and opt in {'cc','exe','sc'}) or opt == 'hierarchical' or (opt is not None and len(opt) > 2 and opt[:2] == 'G='):
            pass
        elif opt is None and arg in source_paths:
            pass
        else:
            result.append(arg)
    require(not skip, 'truncated launcher argv')
    return result


def parse_args(text):
    result = []
    for line in text.splitlines():
        require(not line.startswith('#') and line.strip(), 'unexpected args comments/blank lines')
        result.extend(tokens(line))
    return result


def block_identity(args):
    positions = [i for i, x in enumerate(args) if x == '--hierarchical-block']
    require(len(positions) == 1 and positions[0] + 1 < len(args), 'exactly one hierarchy block required')
    parts = args[positions[0] + 1].split(',')
    require(len(parts) == 2 and parts[0] == ORIGINAL and IDENT.fullmatch(parts[1]), 'original/mangled module binding; no overridden parameters')
    require(re.fullmatch(re.escape(ORIGINAL) + r'_[0-9a-f]{1,63}', parts[1]), 'mangled name outside fixed hierarchical hash family')
    return parts[1], args[positions[0] + 1]


def cmake_lines(text):
    lines = []
    for line in text.splitlines():
        require('\t' not in line and '\r' not in line, 'unexpected CMake controls')
        if not line or line.startswith('#'):
            continue
        require(line == line.strip() and '\\' not in line and ';' not in line and '`' not in line, 'unsupported CMake lexical form')
        lines.append(line)
    return lines


def cmake_contract(text, root, m, mangled, deps):
    p = m['prefix']
    b = 'V' + mangled
    q = lambda s: '"' + s + '"'
    actual = cmake_lines(text)
    solver_lines = [x for x in actual if x.startswith('set(VERILATOR_SOLVER ')]
    require(len(solver_lines) == 1, 'exactly one solver metadata constant')
    solver_match = re.fullmatch(r'set\(VERILATOR_SOLVER \"([A-Za-z0-9_ ./+,:=<>!-]{0,512})\" CACHE STRING \"Default SMT solver for constrained randomization \(from \$VERILATOR_SOLVER\)\"\)', solver_lines[0])
    require(solver_match is not None, 'opaque solver constant syntax')
    solver = solver_match[1]
    sets = {
        'PERL': q(m['perl']) + ' CACHE FILEPATH "Perl executable (from $PERL, defaults to \'perl\' if not set)"',
        'PYTHON3': q(m['python3']) + ' CACHE FILEPATH "Python3 executable (from $PYTHON3, defaults to \'python3\' if not set)"',
        'VERILATOR_ROOT': q(m['verilator_root']) + ' CACHE PATH "Path to Verilator kit (from $VERILATOR_ROOT)"',
        'VERILATOR_SOLVER': q(solver) + ' CACHE STRING "Default SMT solver for constrained randomization (from $VERILATOR_SOLVER)"',
        p+'_USER_CFLAGS': '', p+'_USER_LDLIBS': '',
        p+'_SC': '0',p+'_COVERAGE':'0',p+'_TIMING':'0',p+'_THREADS':'1',p+'_TRACE_VCD':'0',p+'_TRACE_FST':'0',
        p+'_GLOBAL': '"${VERILATOR_ROOT}/include/verilated.cpp" "${VERILATOR_ROOT}/include/verilated_threads.cpp" ',
        p+'_CLASSES_SLOW':'',p+'_CLASSES_FAST':'',p+'_SUPPORT_SLOW':'',p+'_SUPPORT_FAST':'',
        p+'_DEPS': ''.join(q(x)+' ' for x in deps),p+'_USER_CLASSES':''}
    expected = ['set('+k+' '+v+')' for k,v in sets.items()]
    expected += [
        'get_target_property(TOP_TARGET_NAME "${TARGET}" NAME)',
        'add_library('+b+' STATIC)',
        'target_link_libraries(${TOP_TARGET_NAME}  PRIVATE '+b+')',
        'verilate('+b+' PREFIX '+b+' TOP_MODULE '+mangled+' DIRECTORY '+root+'/'+b+' SOURCES  '+''.join(x+' ' for x in m['source_paths'])+' VERILATOR_ARGS -f '+root+'/'+b+'__hierCMakeArgs.f -CFLAGS -fPIC)',
        'verilate(${TOP_TARGET_NAME} PREFIX '+p+' TOP_MODULE '+TOP+' DIRECTORY '+root+' SOURCES  '+root+'/'+b+'/'+mangled+'.sv '+''.join(q(x)+' ' for x in m['source_paths'])+' VERILATOR_ARGS -f '+root+'/'+p+'__hierCMakeArgs.f)']
    require(actual == expected, 'CMake fixed-emitter content/order mismatch')
    return len(actual), solver


def dependency_contract(text, root, names, m):
    lines = text.splitlines()
    require(len(lines) == 1 and lines[0].count(' : ') == 1, 'fixed MMD one-rule format')
    left, right = lines[0].split(' : ')
    ts, ds = left.split(), right.split()
    targets = sorted(root+'/'+x for x in names if not x.endswith('__verFiles.dat'))
    require(ts == targets, 'dependency targets must be exact plan files')
    require(ds and ds[0] == m['backend'], 'dependency executable binding')
    deps = ds[1:]
    require(deps == sorted(set(deps)), 'dependency set ordering/duplicate')
    require(set(m['source_paths']+m['config_paths']).issubset(deps), 'missing declared input dependency')
    require(set(deps).issubset(set(m['dependency_paths'])), 'unknown dependency')
    return deps


def timestamp_contract(text, root, names, deps, m):
    lines = text.splitlines()
    require(len(lines) >= 3 and lines[0] == '# DESCRIPTION: Verilator output: Timestamp data for --skip-identical.  Delete at will.', 'timestamp header')
    require(re.fullmatch(r'C "[^"\r\n]*"', lines[1]), 'timestamp command framing')
    # Raw command line is recorded as opaque compiler metadata, never evaluated.
    entries = {}
    for line in lines[2:]:
        match = re.fullmatch(r'([ST]) +([0-9]+) +([0-9]+) +([0-9]+) +([0-9]+) +([0-9]+) +([0-9]+) "([^"\r\n]+)"', line)
        require(match is not None, 'timestamp row format')
        role = match[1]; path = path_ok(match[8])
        require(path not in entries, 'duplicate timestamp path')
        entries[path] = role
    expected = {x:'S' for x in deps}
    expected.update({root+'/'+x:'T' for x in names})
    require(entries == expected, 'timestamp exact source/target set')
    return len(entries)


def check_tree(root, manifest):
    """Only examines root/plan files. Parent owns whole run-tree/log/cleanup gates."""
    m = manifest.get('plan_contract', manifest)
    root = path_ok(os.fspath(root))
    require(m['top'] == TOP and m['original_module'] == ORIGINAL and IDENT.fullmatch(m['prefix']), 'fixed plan identity')
    require(m['threads'] == 1 and not m.get('library_paths', []), 'one thread/no library-source alternatives')
    required_args = ['--cc','--hierarchical','--make','cmake','-sv','--top-module',TOP,'--prefix',m['prefix'],'--assert','--verilate-jobs','1','--threads','1','--no-timing','--Mdir',root] + m['config_paths'] + m['source_paths']
    require(m['line_args'] == required_args, 'exact plan-only launcher argument contract')
    require(m['perl'] == 'perl' and m['python3'] == 'python3', 'fixed default Perl/Python metadata')
    for path in m['source_paths'] + m['config_paths'] + m['dependency_paths'] + [m['backend'],m['verilator_root']]:
        path_ok(path)
    require(len(m['source_paths']) == len(set(m['source_paths'])) and m['full_sv'] in m['source_paths'], 'source list identity')
    st = os.lstat(root)
    require(stat.S_ISDIR(st.st_mode), 'plan root must be nonsymlink directory')
    names = sorted(os.listdir(root))
    require(len(names) <= 8, 'plan file count cap')
    blobs = {}; signatures = {}; inventory = []; total = 0; total_lines = 0
    for name in names:
        require('/' not in name and re.fullmatch(r'[A-Za-z0-9_.]+', name), 'unsafe output filename')
        path = root+'/'+name; before = os.lstat(path)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_FILE, 'output regular file/size bound')
        with open(path, 'rb') as f:
            require(sig(os.fstat(f.fileno())) == sig(before), 'output changed at open')
            data = f.read(MAX_FILE+1)
            require(len(data) == before.st_size and len(data) <= MAX_FILE, 'output read bound/size')
            require(sig(os.fstat(f.fileno())) == sig(before), 'output changed while read')
        total += len(data); require(total <= MAX_TOTAL, 'aggregate plan byte cap')
        require(b'\x00' not in data and b'\r' not in data, 'binary/control output rejected')
        for line in data.splitlines(keepends=True):
            total_lines += 1
            require(len(line) <= MAX_LINE and total_lines <= MAX_LINES, 'plan line bounds')
        text = data.decode('ascii'); require(text.endswith('\n'), 'unterminated emitted file')
        blobs[name] = text; signatures[name] = sig(before)
        inventory.append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    p = m['prefix']; topfile = p+'__hierCMakeArgs.f'
    require(topfile in blobs, 'missing top argument file')
    top_args = parse_args(blobs[topfile])
    mangled, hierarchy = block_identity(top_args)
    b = 'V'+mangled
    expected_names = sorted([p+'.cmake',topfile,b+'__hierCMakeArgs.f',p+'__ver.d',p+'__verFiles.dat'])
    require(names == expected_names, 'exact five plan-only files; codegen/typeparam/ELF forbidden')
    require(top_args == ['--hierarchical-block',hierarchy,'--threads','1','--cc'] + forwarded(m['line_args'],m['source_paths'],True), 'top args content/order')
    child_expected = ['--cc','--prefix',b,'--mod-prefix',b,'--top-module',mangled,'--lib-create',mangled,'--hierarchical-child','1','--hierarchical-block',hierarchy] + forwarded(m['line_args'],m['source_paths'],False)
    require(parse_args(blobs[b+'__hierCMakeArgs.f']) == child_expected, 'child args content/order')
    deps = dependency_contract(blobs[p+'__ver.d'],root,names,m)
    ncommands, solver = cmake_contract(blobs[p+'.cmake'],root,m,mangled,deps)
    ntimestamps = timestamp_contract(blobs[p+'__verFiles.dat'],root,names,deps,m)
    require(sorted(os.listdir(root)) == names, 'output set changed')
    for name in names:
        require(sig(os.lstat(root+'/'+name)) == signatures[name], 'output stat changed')
    return {'status':'PASS_FIXED_5032_CMAKE_MODULE_PLAN_ONLY','files':inventory,'bytes':total,'lines':total_lines,'module_plan_count':1,'original_module':ORIGINAL,'mangled_module':mangled,'effective_seed_from_pinned_source':0,'overridden_parameter_count':0,'opaque_solver_metadata':solver,'top':TOP,'cmake_commands':ncommands,'timestamp_entries':ntimestamps,'cpp_generated':False,'binary_built':False,'model_executed':False,'eight_state_instances_verified':False,'numerical_pass':False,'dependency_paths':deps}
