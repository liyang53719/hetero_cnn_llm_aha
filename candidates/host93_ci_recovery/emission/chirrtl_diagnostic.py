"""Pinned, isolated Host93 CHIRRTL diagnostic; no child runner or execution CLI.

The coordinator supplies its same-buffer verified original host_emission module
and this module's pinned emitter bytes. Original assembly is never modified.
Only call_phase owns children. The diagnostic performs no firtool, SV, native
build, or Host execution. A separate exact-historical-FIR resume permits SV.
"""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Require Python -I -S -B before any project load.')

import hashlib
from pathlib import Path
import re
import stat
import time

MIB = 1024 * 1024
FIR_CAP = 96 * MIB
BASE_MODULE_PIN = {'bytes': 26517, 'sha256': 'f1cb8595247b2c991c77e4fa7404fc1cd618bb28f9e173eb43d7e00a58c49b50'}
ORIGINAL_EMITTER_PIN = {'bytes': 2262, 'sha256': 'ebc35a597dc3be2374efa7408ea152ff954f37483132b1d03e0d8c902628705d'}
EMITTER_PIN = {'bytes': 3520, 'sha256': 'f4fb8ca9666fc97e4d2bcc9f883d8e1c066d1ec80fc7c13c1a91d388f253bc2f'}
HISTORICAL_FIR_PIN = {'bytes': 42417256, 'sha256': '264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a'}
DIAGNOSTIC_LIMITS = {'total_seconds': 90, 'work_seconds': 60, 'cpu_seconds': 60,
                     'as_bytes': 4 * 1024 * MIB, 'fsize_bytes': FIR_CAP,
                     'log_bytes': 2 * MIB, 'sample_rows': 100}
METRICS = ('utf8_bytes', 'line_count', 'module_count', 'extmodule_count',
           'source_info_count', 'source_info_utf8_bytes', 'project_source_info_count',
           'library_source_info_count', 'other_source_info_count')
MARKER = b'CANONICAL_HOST93_CHIRRTL_DIAGNOSTIC '
SOURCE_INFO = re.compile(r'@\[[^\]\r\n]*\]')


SAFE_CONTRACT_CODES = ('DIAGNOSTIC_CONTRACT', 'DIAGNOSTIC_EMITTER', 'DIAGNOSTIC_DERIVATION',
                       'DIAGNOSTIC_STATS', 'DIAGNOSTIC_FIR_OUTPUT', 'DIAGNOSTIC_RESUME_IDENTITY')


class DiagnosticContractError(ValueError):
    safe_contract_boundary = 'CHIRRTL_DIAGNOSTIC'

    def __init__(self, reason, code='DIAGNOSTIC_CONTRACT'):
        if code not in SAFE_CONTRACT_CODES:
            raise ValueError('unknown diagnostic contract code')
        super().__init__(reason)
        self.safe_contract_code = code


def need(condition, reason, code='DIAGNOSTIC_CONTRACT'):
    if not condition:
        raise DiagnosticContractError(reason, code)


def validate_emitter(raw):
    need(type(raw) is bytes and len(raw) == EMITTER_PIN['bytes'] and
         hashlib.sha256(raw).hexdigest() == EMITTER_PIN['sha256'],
         'fixed derived emitter bytes required before any write or child', 'DIAGNOSTIC_EMITTER')
    return raw


def parse_observation(raw_log):
    """Extract only fixed numeric fields, including from a retained failed log.

    This does not establish successful emission or historical identity. It also
    accepts measured size above the output cap: the marker precedes that guard.
    """
    need(type(raw_log) is bytes and len(raw_log) <= 2 * MIB, 'bounded raw diagnostic log required')
    need(raw_log.count(MARKER) == 1, 'exact diagnostic marker required')
    rows = [line for line in raw_log.splitlines() if line.startswith(MARKER)]
    need(len(rows) == 1 and len(rows[0]) <= 512, 'standalone bounded diagnostic marker required', 'DIAGNOSTIC_STATS')
    expression = re.escape(MARKER) + b' '.join(
        key.encode('ascii') + rb'=([0-9]{1,12})' for key in METRICS)
    match = re.fullmatch(expression, rows[0])
    need(match is not None, 'fixed numeric diagnostic marker required', 'DIAGNOSTIC_STATS')
    values = dict(zip(METRICS, map(int, match.groups())))
    need(values['utf8_bytes'] > 0 and values['line_count'] > 0 and values['module_count'] > 0,
         'nonempty CHIRRTL diagnostic required')
    need(all(values[key] <= values['utf8_bytes'] for key in METRICS[1:]), 'diagnostic counts exceed byte count')
    need(sum(values[key] for key in ('project_source_info_count', 'library_source_info_count',
                                    'other_source_info_count')) == values['source_info_count'],
         'source-info category partition mismatch', 'DIAGNOSTIC_STATS')
    return values


def measure_fir(raw):
    """Independently check bounded FIR metrics with the emitter's exact regexes."""
    need(type(raw) is bytes and 0 < len(raw) <= FIR_CAP, 'bounded fresh FIR bytes required')
    text = raw.decode('utf-8', errors='strict')
    tags = SOURCE_INFO.finditer(text)
    count, size, project, library = 0, 0, 0, 0
    for tag in tags:
        count += 1
        size += len(tag.group(0).encode('utf-8'))
        project += int(tag.group(0).startswith('@[scala/'))
        library += int(tag.group(0).startswith('@[src/'))
    return {'utf8_bytes': len(raw), 'line_count': text.count('\n') + int(not text.endswith('\n')),
            'module_count': len(re.findall(r'(?m)^  module [^\r\n]*:', text)),
            'extmodule_count': len(re.findall(r'(?m)^  extmodule [^\r\n]*:', text)),
            'source_info_count': count, 'source_info_utf8_bytes': size,
            'project_source_info_count': project, 'library_source_info_count': library,
            'other_source_info_count': count - project - library}


def derive_sources(base, assembled, destination, plan, emitter_raw):
    """Copy the original 93 exact buffers, replacing only the pinned emitter."""
    validate_emitter(emitter_raw)
    assembled, destination = base.clean(assembled), base.clean(destination)
    need(not destination.exists() and destination.parent.is_dir(), 'fresh derived source root required')
    need(not destination.is_relative_to(assembled) and not assembled.is_relative_to(destination),
         'original and derived source roots must be disjoint')
    expected = dict(plan['expected93'])
    need(len(expected) == 93, 'original exact93 source map required')
    target = base.relative(plan['emitter']['target'])
    need(expected.get(target) == ORIGINAL_EMITTER_PIN['sha256'], 'original emitter target identity')
    original_inventory = base.inventory(assembled, 16*MIB, 2*MIB)
    need(set(original_inventory['files']) == {'scala/' + name for name in expected} | {'SOURCE_RECEIPT.json'},
         'original assembly complete inventory')
    for name, digest in expected.items():
        base.relative(name)
        need(original_inventory['files']['scala/' + name]['sha256'] == digest, 'original assembly differs')
    original = base.read_bytes(assembled / 'scala' / target, ORIGINAL_EMITTER_PIN['bytes'], ORIGINAL_EMITTER_PIN)
    anchor = b'  val bytes = ir.getBytes(StandardCharsets.UTF_8)\n'
    need(original.count(anchor) == emitter_raw.count(anchor) == 1 and
         original.split(anchor, 1)[0] == emitter_raw.split(anchor, 1)[0],
         'emitter elaboration lines must remain byte-identical', 'DIAGNOSTIC_DERIVATION')
    destination.mkdir(mode=0o700)
    derived_pins = {}
    for name in sorted(expected):
        original_pin = original_inventory['files']['scala/' + name]
        raw = base.read_bytes(assembled / 'scala' / name, 2*MIB, original_pin)
        if name == target:
            raw = emitter_raw
        derived_pins['scala/' + name] = base.byte_identity(raw)
        base.write_new(destination / 'scala' / name, raw)
    expected[target] = EMITTER_PIN['sha256']
    actual = base.inventory(destination, 16*MIB, 2*MIB)
    base.exact_files(actual, derived_pins)
    need(len(actual['files']) == 93 and all(actual['files']['scala/' + name]['sha256'] == digest
                                         for name, digest in expected.items()), 'derived exact93 source map')
    base.exact_files(base.inventory(assembled, 16*MIB, 2*MIB), original_inventory['files'])
    return expected, actual, {'base_module': dict(BASE_MODULE_PIN), 'original_emitter': dict(ORIGINAL_EMITTER_PIN),
                             'derived_emitter': dict(EMITTER_PIN), 'emitter_target': target,
                             'preserved_source_count': 92, 'derived_source_count': 93,
                             'original_expected93': plan['expected93'], 'derived_expected93': expected,
                             'compiler_project_root_is_derived_parent_of_scala': True,
                             'arithmetic_source_changed': False, 'original_assembly_modified': False}


def compiler_command(helper, java, jars, classes, source, expected, jplan):
    """SourceInfoFileResolver reads this JVM property while Scala compiles."""
    source = Path(source)
    need(source.is_absolute() and source.name == 'scala', 'fixed derived Scala source root')
    argv = list(helper.command(java, jars, classes, source, expected, jplan))
    need(argv and str(argv[0]) == str(java) and 'scala.tools.nsc.Main' in argv,
         'reviewed Scala compiler command required')
    need(not any(str(item).startswith('-Dchisel.project.root=') for item in argv), 'duplicate compiler source root')
    argv.insert(1, '-Dchisel.project.root=' + str(source.parent))
    return argv


def run(repo, work, call_phase, base, emitter_raw):
    """Run exactly six coordinator-owned phases, returning measured diagnostic FIR.

    base is the coordinator's unchanged, same-buffer-loaded host_emission.py.
    emitter_raw is the coordinator's fixed source buffer, revalidated here before
    writes. No result constitutes Host, numerical, SV, or full-block qualification.
    The caller retains bounded raw failure logs and owns all child supervision.
    """
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use Python -I -S -B')
    validate_emitter(emitter_raw)
    repo, work = base.clean(repo), base.clean(work)
    need(repo.is_dir() and (repo / '.git').exists(), 'existing repository checkout required')
    need(work.parent.is_dir() and not work.exists(), 'fresh work directory required')
    need(not work.is_relative_to(repo) and not repo.is_relative_to(work), 'work must be disjoint from repository')
    need(callable(call_phase), 'bounded phase callback required')
    work.mkdir(mode=0o700)
    result = {'status': 'INCOMPLETE_HOST93_CHIRRTL_DIAGNOSTIC', 'phases': {}, 'inventories': {},
              'identities': {}, 'historical95_identity_inherited': False, 'host_executed': False,
              'numerical_qualification': False, 'full_block_rtl_passes': 0,
              'firtool_executed': False, 'rtl_generated': False}
    try:
        pins = base.source_pins()
        need(len(pins) == 121, 'fixed source pin count')
        frozen = work / 'frozen_repo'
        frozen.mkdir()
        source_raw = {}
        for name, pin in pins.items():
            raw = base.read_bytes(repo / name, pin['bytes'], pin)
            source_raw[name] = raw
            base.write_new(frozen / name, raw)
        frozen_inventory = base.inventory(frozen, 4*MIB, 2*MIB)
        base.exact_files(frozen_inventory, pins)
        result['inventories']['fixed_source_inputs'] = frozen_inventory
        plan = base.unique_json(source_raw[base.REPLAY])
        need(len(plan['input_sha256']) == 111 and len(plan['expected93']) == 93, 'Host93 input/source cardinality')
        for name, digest in plan['input_sha256'].items():
            need(pins[name]['sha256'] == digest, 'replay/source pins disagree')
        jplan, hplan = [base.unique_json(source_raw[base.BASE + 'acquisition/plans/' + group + '.json'])
                        for group in ('jar87', 'hardfloat20')]
        need(len(jplan['artifacts']) == 87 and len(hplan['artifacts']) == 20, 'fixed JAR87 and HardFloat20 closure')
        class_helper = base.load_source(frozen / base.CLASS_HELPER, source_raw[base.CLASS_HELPER], pins[base.CLASS_HELPER])
        chirrtl_helper = base.load_source(frozen / base.CHIRRTL_HELPER, source_raw[base.CHIRRTL_HELPER], pins[base.CHIRRTL_HELPER])
        java_home, java, java_pin = base._java21()
        python = base.clean(Path(sys.executable).resolve(strict=True))
        python_pin = base.file_identity(python, 64*MIB)
        result['identities'].update({'java21': java_pin, 'python': python_pin})
        result['paths'] = {'java_home': str(java_home), 'java': str(java), 'python': str(python)}
        for name in ('home', 'tmp', 'phases'):
            (work / name).mkdir()
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
               'JAVA_HOME': str(java_home), 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'PYTHONHASHSEED': '0'}

        def phase(name, argv):
            limits = dict(DIAGNOSTIC_LIMITS if name == 'chirrtl_diagnostic' else base.LIMITS[name])
            phase_cwd = work / 'phases' / name
            phase_cwd.mkdir()
            need(base.file_identity(python, 64*MIB) == python_pin, 'Python changed before phase')
            start = time.monotonic()
            value = call_phase('host93_' + name, list(map(str, argv)), phase_cwd,
                               base.phase_environment(name, env), limits)
            result['phases'][name] = base._accept_phase(value)
            result['inventories']['phase_cwd_' + name] = base.inventory(phase_cwd, 64*MIB, 48*MIB)
            need(time.monotonic() - start <= limits['total_seconds'], 'phase total deadline exceeded')
            need(base.file_identity(python, 64*MIB) == python_pin, 'Python changed after phase')
            return value['raw_log']

        def script(name, source, argv):
            raw = base.read_bytes(frozen / source, pins[source]['bytes'], pins[source])
            need(raw == source_raw[source], 'script snapshot changed')
            return phase(name, [python, '-I', '-S', '-B', '-c', base.BOOTSTRAP, frozen / source,
                                pins[source]['bytes'], pins[source]['sha256'], *argv])

        def stable_inputs():
            base.exact_files(base.inventory(frozen, 4*MIB, 2*MIB), pins)
            need(base.file_identity(java, 64*MIB) == java_pin['java'] and
                 base.file_identity(java_home / 'release', MIB) == java_pin['release'], 'Java inputs changed')

        log = phase('java_version', [java, '-Xmx64m', '-XX:ActiveProcessorCount=1', '-version'])
        need(re.search(rb'(?:openjdk|java) version "21(?:[.\-+"])', log), 'Java 21 version probe failed')
        stable_inputs()
        acquired = work / 'acquired'
        acquired.mkdir()
        jars, hf = (acquired / name for name in ('jar87', 'hardfloat20'))
        for group, destination, ap, cap in (('jar87', jars, jplan, 514*MIB), ('hardfloat20', hf, hplan, 3*MIB)):
            script('acquire_' + group, base.ACQUIRER, ['fetch', group, '--repository', repo,
                   '--output-root', destination, '--execute-acquisition'])
            actual = base._acquired(destination, ap, {'ACQUISITION.json'}, cap)
            result['inventories'][group] = actual
            stable_inputs()
        assembled = work / 'assembled'
        base.exact_files(base.inventory(hf, 3*MIB, 2*MIB), result['inventories']['hardfloat20']['files'])
        script('assemble', base.ASSEMBLER, ['--repo', frozen, '--assemble-reviewed-source',
               '--hardfloat-scala', hf / 'hardfloat/src/main/scala', '--output', assembled])
        derived = work / 'derived'
        expected, derived_inventory, derivation = derive_sources(base, assembled, derived, plan, emitter_raw)
        assembly = base.inventory(assembled, 16*MIB, 2*MIB)
        result['inventories']['assembled'] = assembly
        result['inventories']['derived'] = derived_inventory
        result['derivation'] = derivation
        base.save(work / 'CHIRRTL_DERIVATION.json', derivation)
        base.exact_files(base.inventory(hf, 3*MIB, 2*MIB), result['inventories']['hardfloat20']['files'])
        stable_inputs()
        classes = work / 'classes'
        classes.mkdir()
        source = derived / 'scala'

        def stable_emission_inputs():
            base.exact_files(base.inventory(assembled, 16*MIB, 2*MIB), assembly['files'])
            base.exact_files(base.inventory(derived, 16*MIB, 2*MIB), derived_inventory['files'])
            base.exact_files(base.inventory(jars, 514*MIB, 64*MIB), result['inventories']['jar87']['files'])
            stable_inputs()

        stable_emission_inputs()
        phase('class', compiler_command(class_helper, java, jars, classes, source, expected, jplan))
        class_inventory = base.inventory(classes, 64*MIB, 48*MIB)
        result['inventories']['classes'] = class_inventory
        need(class_inventory['files'] and all(name.endswith('.class') for name in class_inventory['files']),
             'nonempty class-only output required')
        need('heteronpu/continuous/EmitCanonicalHost93.class' in class_inventory['files'], 'Host93 emitter class missing')
        stable_emission_inputs()
        structure = work / 'structure'
        base.exact_files(base.inventory(classes, 64*MIB, 48*MIB), class_inventory['files'])
        log = phase('chirrtl_diagnostic', chirrtl_helper.command(java, classes, jars, jplan, structure))
        emitted_observation = parse_observation(log)
        need(log.count(b'CANONICAL_HOST93_CHIRRTL_BEGIN ') == 1 and
             log.count(b'CANONICAL_HOST93_CHIRRTL_WRITTEN ') == 1, 'exact Host93 emitter markers required')
        structure_inventory = base.inventory(structure, FIR_CAP, FIR_CAP, 16, 8)
        result['inventories']['chirrtl'] = structure_inventory
        need(set(structure_inventory['files']) == {'HostBlockCollection.fir'}, 'exact fresh diagnostic FIR output', 'DIAGNOSTIC_FIR_OUTPUT')
        fir = structure / 'HostBlockCollection.fir'
        pin = structure_inventory['files']['HostBlockCollection.fir']
        fir_raw = base.read_bytes(fir, FIR_CAP, pin)
        observed = measure_fir(fir_raw)
        need(observed == emitted_observation, 'numeric marker differs from measured FIR', 'DIAGNOSTIC_STATS')
        observed['historical_fir_equal'] = pin == HISTORICAL_FIR_PIN
        result['observation'] = observed
        result['fir'] = {'path': str(fir), **pin}
        result['identities']['fir'] = pin
        base.exact_files(base.inventory(classes, 64*MIB, 48*MIB), class_inventory['files'])
        stable_emission_inputs()
        base.exact_files(base.inventory(hf, 3*MIB, 2*MIB), result['inventories']['hardfloat20']['files'])
        result['status'] = 'PASS_HOST93_CHIRRTL_DIAGNOSTIC_ONLY'
        result['structural_assertions_passed'] = True
        base.save(work / 'CHIRRTL_DIAGNOSTIC_RESULT.json', result)
        result['resume_context'] = {'work': str(work), 'receipt_identity': base.file_identity(
            work / 'CHIRRTL_DIAGNOSTIC_RESULT.json', 2*MIB)}
        return result
    except BaseException as error:
        result['status'] = 'INCOMPLETE_HOST93_CHIRRTL_DIAGNOSTIC'
        result['error_type'] = type(error).__name__
        try:
            base.save(work / 'CHIRRTL_DIAGNOSTIC_FAILED.json', result)
        except BaseException as receipt_error:
            if hasattr(error, 'add_note'):
                error.add_note('Failure receipt error: ' + type(receipt_error).__name__)
        raise


def resume_sv(repo, work, call_phase, base, context):
    """Resume only acquire_firtool/SV, in the same diagnostic work directory.

    context is the live run result's private resume_context, binding its persisted
    diagnostic receipt. No acquisition, assembly, CLASS, or CHIRRTL is repeated.
    The exact historical FIR and original Host/provider assertions are mandatory.
    """
    need(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'use Python -I -S -B')
    repo, work = base.clean(repo), base.clean(work)
    need(type(context) is dict and set(context) == {'work', 'receipt_identity'} and
         context['work'] == str(work) and work.is_dir() and callable(call_phase),
         'same diagnostic work and receipt context required', 'DIAGNOSTIC_RESUME_IDENTITY')
    need(repo.is_dir() and (repo / '.git').exists() and not work.is_relative_to(repo) and
         not repo.is_relative_to(work), 'disjoint existing repository and diagnostic work', 'DIAGNOSTIC_RESUME_IDENTITY')
    receipt_pin = context['receipt_identity']
    need(type(receipt_pin) is dict and set(receipt_pin) == {'bytes', 'sha256'} and
         type(receipt_pin['bytes']) is int and 0 < receipt_pin['bytes'] <= 2*MIB and
         type(receipt_pin['sha256']) is str and re.fullmatch('[a-f0-9]{64}', receipt_pin['sha256']),
         'bounded diagnostic receipt identity', 'DIAGNOSTIC_RESUME_IDENTITY')
    result = base.unique_json(base.read_bytes(work / 'CHIRRTL_DIAGNOSTIC_RESULT.json', 2*MIB, receipt_pin))
    need(result['status'] == 'PASS_HOST93_CHIRRTL_DIAGNOSTIC_ONLY' and
         result['structural_assertions_passed'] is True and result['observation']['historical_fir_equal'] is True and
         result['identities']['fir'] == HISTORICAL_FIR_PIN and base.FIR_PIN == HISTORICAL_FIR_PIN,
         'resume requires exact historical FIR and passed structural assertions', 'DIAGNOSTIC_RESUME_IDENTITY')
    need(result['fir'] == {'path': str(work / 'structure/HostBlockCollection.fir'), **HISTORICAL_FIR_PIN} and
         all(result[key] is False for key in ('historical95_identity_inherited', 'host_executed',
                                              'numerical_qualification', 'firtool_executed', 'rtl_generated')) and
         result['full_block_rtl_passes'] == 0, 'diagnostic result scope changed', 'DIAGNOSTIC_RESUME_IDENTITY')
    try:
        pins = base.source_pins()
        frozen, assembled, derived = (work / name for name in ('frozen_repo', 'assembled', 'derived'))
        classes, jars, hf = work / 'classes', work / 'acquired/jar87', work / 'acquired/hardfloat20'
        fir = work / 'structure/HostBlockCollection.fir'
        base.exact_files(base.inventory(frozen, 4*MIB, 2*MIB), pins)
        raw_plan = base.read_bytes(frozen / base.REPLAY, pins[base.REPLAY]['bytes'], pins[base.REPLAY])
        plan = base.unique_json(raw_plan)
        need(len(plan['input_sha256']) == 111 and len(plan['expected93']) == 93 and len(pins) == 121,
             'fixed resume source closure', 'DIAGNOSTIC_RESUME_IDENTITY')
        expected = dict(plan['expected93'])
        target = base.relative(plan['emitter']['target'])
        need(expected[target] == ORIGINAL_EMITTER_PIN['sha256'], 'resume original emitter pin', 'DIAGNOSTIC_RESUME_IDENTITY')
        expected[target] = EMITTER_PIN['sha256']
        need(result['derivation']['original_expected93'] == plan['expected93'] and
             result['derivation']['derived_expected93'] == expected and
             result['derivation']['derived_emitter'] == EMITTER_PIN,
             'resume derived source identity', 'DIAGNOSTIC_RESUME_IDENTITY')
        for name, digest in plan['expected93'].items():
            need(result['inventories']['assembled']['files']['scala/' + name]['sha256'] == digest,
                 'resume assembly expected93 identity', 'DIAGNOSTIC_RESUME_IDENTITY')
        need(set(result['inventories']['derived']['files']) == {'scala/' + name for name in expected} and
             all(result['inventories']['derived']['files']['scala/' + name]['sha256'] == digest
                 for name, digest in expected.items()), 'resume derived expected93 identity', 'DIAGNOSTIC_RESUME_IDENTITY')
        fplan_name = base.BASE + 'acquisition/plans/firtool.json'
        fplan = base.unique_json(base.read_bytes(frozen / fplan_name, pins[fplan_name]['bytes'], pins[fplan_name]))
        helper_raw = base.read_bytes(frozen / base.SV_HELPER, pins[base.SV_HELPER]['bytes'], pins[base.SV_HELPER])
        sv_helper = base.load_source(frozen / base.SV_HELPER, helper_raw, pins[base.SV_HELPER])
        java_home, java, java_pin = base._java21()
        python = base.clean(Path(sys.executable).resolve(strict=True))
        python_pin = base.file_identity(python, 64*MIB)
        need(result['paths'] == {'java_home': str(java_home), 'java': str(java), 'python': str(python)} and
             result['identities']['java21'] == java_pin and result['identities']['python'] == python_pin,
             'resume runtime inputs changed', 'DIAGNOSTIC_RESUME_IDENTITY')
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(work / 'home'), 'TMPDIR': str(work / 'tmp'),
               'JAVA_HOME': str(java_home), 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'PYTHONHASHSEED': '0'}

        def stable_inputs():
            base.exact_files(base.inventory(frozen, 4*MIB, 2*MIB), pins)
            for name, root, total, single in (
                    ('assembled', assembled, 16*MIB, 2*MIB), ('derived', derived, 16*MIB, 2*MIB),
                    ('classes', classes, 64*MIB, 48*MIB), ('jar87', jars, 514*MIB, 64*MIB),
                    ('hardfloat20', hf, 3*MIB, 2*MIB)):
                base.exact_files(base.inventory(root, total, single), result['inventories'][name]['files'])
            need(base.file_identity(fir, 48*MIB) == HISTORICAL_FIR_PIN and
                 base.file_identity(java, 64*MIB) == java_pin['java'] and
                 base.file_identity(java_home / 'release', MIB) == java_pin['release'] and
                 base.file_identity(python, 64*MIB) == python_pin,
                 'resume execution inputs changed', 'DIAGNOSTIC_RESUME_IDENTITY')
            base.read_bytes(work / 'CHIRRTL_DIAGNOSTIC_RESULT.json', 2*MIB, receipt_pin)

        def phase(name, argv):
            stable_inputs()
            phase_cwd = work / 'phases' / name
            phase_cwd.mkdir()
            start = time.monotonic()
            value = call_phase('host93_' + name, list(map(str, argv)), phase_cwd,
                               base.phase_environment(name, env), dict(base.LIMITS[name]))
            result['phases'][name] = base._accept_phase(value)
            result['inventories']['phase_cwd_' + name] = base.inventory(phase_cwd, 64*MIB, 48*MIB)
            need(time.monotonic() - start <= base.LIMITS[name]['total_seconds'], 'resume phase deadline exceeded')
            stable_inputs()
            return value['raw_log']

        def script(name, source, argv):
            base.read_bytes(frozen / source, pins[source]['bytes'], pins[source])
            return phase(name, [python, '-I', '-S', '-B', '-c', base.BOOTSTRAP, frozen / source,
                                pins[source]['bytes'], pins[source]['sha256'], *argv])

        stable_inputs()
        ft = work / 'acquired/firtool'
        script('acquire_firtool', base.MEMBER_HELPER, ['--acquisition-source', frozen / (base.BASE + 'acquisition'),
               '--repository', repo, '--output-root', ft, '--execute-reviewed-acquisition'])
        tool_inventory = base._acquired(ft, fplan, {'firtool', 'ACQUISITION.json', 'MEMBER.json'}, 100*MIB)
        result['inventories']['firtool_acquisition'] = tool_inventory
        need(tool_inventory['files']['firtool'] == base.FIRTOOL_PIN, 'official firtool member identity mismatch')
        need(stat.S_IMODE((ft / 'firtool').stat().st_mode) == 0o600, 'acquired member must remain mode0600')
        member_receipt = base.unique_json(base.read_bytes(ft / 'MEMBER.json', MIB))
        need(member_receipt['extracted_member_count'] == 1 and member_receipt['binary_executed'] is False and
             member_receipt['member_name'] == 'org.chipsalliance/llvm-firtool/linux-x64/bin/firtool',
             'single-member extraction receipt')
        tool = work / 'tool/firtool'
        base.write_new(tool, base.read_bytes(ft / 'firtool', base.FIRTOOL_PIN['bytes'], base.FIRTOOL_PIN), 0o700)
        need(base.file_identity(tool, 32*MIB) == base.FIRTOOL_PIN, 'execution snapshot identity')
        rtl = work / 'rtl'
        rtl.mkdir()
        stable_inputs()
        need(base.file_identity(tool, 32*MIB) == base.FIRTOOL_PIN, 'SV preflight firtool changed')
        result['firtool_executed'] = None
        result['rtl_generated'] = None
        phase('sv', sv_helper.command(tool, fir, rtl))
        result['firtool_executed'] = True
        rtl_inventory = base.inventory(rtl, 256*MIB, 128*MIB, 64, 32)
        result['inventories']['rtl'] = rtl_inventory
        need({'HostBlockCollection.sv'} <= set(rtl_inventory['files']) <= {'HostBlockCollection.sv', 'circt.anno.json'},
             'unexpected SV output files')
        result['identities']['sv'] = rtl_inventory['files']['HostBlockCollection.sv']
        need(result['identities']['sv'] == base.SV_PIN, 'fresh SV deterministic identity mismatch')
        if 'circt.anno.json' in rtl_inventory['files']:
            need(rtl_inventory['files']['circt.anno.json']['bytes'] <= 32*MIB, 'annotation byte cap')
        need(base.file_identity(fir, 48*MIB) == HISTORICAL_FIR_PIN and
             base.file_identity(tool, 32*MIB) == base.FIRTOOL_PIN, 'SV inputs changed')
        base.exact_files(base.inventory(ft, 100*MIB, 64*MIB), tool_inventory['files'])
        stable_inputs()
        result['paths'].update({name: str(path) for name, path in {
            'source': derived / 'scala', 'classes': classes, 'jars': jars, 'hardfloat': hf,
            'fir': fir, 'sv': rtl / 'HostBlockCollection.sv', 'firtool': tool, 'frozen_repo': frozen}.items()})
        result['inventories']['complete_work_before_result_receipt'] = base.inventory(work, 1024*MIB, 128*MIB, 40000, 20000)
        result['status'] = 'PASS_HOST93_FRESH_EMISSION_ONLY'
        result['identities']['firtool'] = base.file_identity(tool, 32*MIB)
        for name, path in (('fir', fir), ('sv', rtl / 'HostBlockCollection.sv'), ('firtool', tool)):
            result[name] = {'path': str(path), **result['identities'][name],
                            'mode': format(stat.S_IMODE(path.stat().st_mode), '04o')}
        result['firtool_executed'] = True
        result['rtl_generated'] = True
        base.save(work / 'HOST_EMISSION_RESULT.json', result)
        return result
    except BaseException as error:
        result['status'] = 'INCOMPLETE_HOST93_RESUMED_SV'
        result['error_type'] = type(error).__name__
        try:
            base.save(work / 'HOST_EMISSION_FAILED.json', result)
        except BaseException as receipt_error:
            if hasattr(error, 'add_note'):
                error.add_note('Failure receipt error: ' + type(receipt_error).__name__)
        raise
