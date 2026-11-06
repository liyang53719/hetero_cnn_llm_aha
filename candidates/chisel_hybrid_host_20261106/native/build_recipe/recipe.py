"""Validate and display an unrun native build description. There is no executor."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import re
import types

D = Path(__file__).resolve().parent
REPO = D.parents[3]
TOKEN = re.compile(r'\{([^{}]+)\}')
# Filled only from the final independently reviewed fixed component descriptions.
CONTRACT_DIGESTS = {'matrix_icg': 'a306e4eeda82841451b607ecad23d2fd73d7d1aca3df041733994c2641947cda',
                    'idma': '10b900c3490f8e22c36c28f0451498fe3807b44f56b70c8bc20f76d73365efde'}
FRAGMENTS_SHA256 = '1b02176e9640c3af35c68bc6c08010375b566bfe808fd6051297c55ea035ed86'


def need(value, message):
    if not value:
        raise ValueError(message)


def relative(value):
    need(type(value) is str and value, 'nonempty relative source path')
    path = PurePosixPath(value)
    need(not path.is_absolute() and '..' not in path.parts and str(path) == value, 'canonical source-relative path')
    return path


def validate_fragment(fragment):
    # Round-trip without an object hook: contracts must contain plain JSON data.
    json.loads(json.dumps(fragment, allow_nan=False))
    need(fragment['schema'] == 'PORTABLE_NATIVE_RECIPE_FRAGMENT_V1', 'fragment schema')
    need(fragment['status'] == 'UNRUN_PORTABLE_BUILD_RECIPE' and fragment['execution_authority'] is False, 'unrun source-only scope')
    need(re.fullmatch('[a-z][a-z0-9_]*', fragment['component']), 'component name')
    need(re.fullmatch('[0-9a-f]{40}', fragment['repository_commit']), 'source repository basis')
    rows = fragment['inputs']
    need(len(rows) == len({r['path'] for r in rows}) == len({r['role'] for r in rows}), 'unique repository input paths and roles')
    for row in rows:
        relative(row['path'])
        need(re.fullmatch('[0-9a-f]{64}', row['sha256']), 'repository source identity')
    tools = fragment['tools']
    need(len(tools) == len({tool['id'] for tool in tools}), 'unique tool roles')
    tool_ids = {tool['id'] for tool in tools}
    need(all(type(x) is str and x for x in tool_ids), 'named tool prerequisites')
    for tool in tools:
        need(type(tool.get('version')) is str and tool['version'], 'tool version prerequisite')
        prior = tool.get('prior_binary_sha256')
        if prior is None:
            need(tool.get('identity_status') == 'UNRESOLVED' and type(tool.get('identity_prerequisite')) is str and tool['identity_prerequisite'], 'missing tool identity remains an explicit unresolved prerequisite')
        else:
            need(type(prior) is str and re.fullmatch('[0-9a-f]{64}', prior), 'historical tool identity, not fresh qualification')
        need(type(tool.get('required_components')) is list and tool['required_components'], 'complete tool component prerequisites declared')
    artifacts = fragment['artifacts']
    need(type(artifacts) is dict and all(type(x) is str and x for x in artifacts), 'explicit artifact placeholders')
    stages = fragment['stages']
    need(len(stages) == len({stage['id'] for stage in stages}), 'unique ordered build stages')
    outputs = [role for stage in stages for role in stage['outputs']]
    need(len(outputs) == len(set(outputs)), 'unique produced artifact roles')
    prerequisites = fragment['prerequisite_roles']
    aggregates = fragment['aggregate_roles']
    need(type(prerequisites) is dict and type(aggregates) is dict, 'explicit prerequisite and aggregate role catalogs')
    source_roles = {row['role'] for row in rows}
    need(not (set(outputs) & (source_roles | set(prerequisites) | set(aggregates))), 'distinct source, prerequisite, aggregate and produced roles')
    need(not (source_roles & (set(prerequisites) | set(aggregates))) and not (set(prerequisites) & set(aggregates)), 'unambiguous initial role definitions')
    available = set(source_roles)

    def require_available(role, seen=()):
        need(type(role) is str and role not in seen, 'acyclic named input role')
        if role in aggregates:
            members = aggregates[role]
            need(type(members) is list and members and len(members) == len(set(members)), 'nonempty unique aggregate members')
            for member in members:
                require_available(member, seen + (role,))
        elif role in prerequisites:
            descriptor = prerequisites[role]
            need(isinstance(descriptor, (str, dict)) and descriptor, 'explicit unresolved prerequisite description')
            if isinstance(descriptor, dict):
                for dependency in descriptor.get('requires', []):
                    require_available(dependency, seen + (role,))
        else:
            need(role in available, 'input role requires an earlier producer or explicit prerequisite: ' + role)

    for stage in stages:
        need(stage['unexecuted'] is True, 'new portable stage remains unexecuted')
        need(type(stage['argv']) is list and stage['argv'] and all(type(x) is str and x for x in stage['argv']), 'tokenized argv, never a shell command')
        executable = TOKEN.fullmatch(stage['argv'][0])
        need(executable is not None and executable[1].startswith('tool:') and executable[1][5:] in tool_ids, 'explicit declared build tool')
        cwd = stage['cwd']
        need(type(cwd) is str and (cwd == '{build}' or cwd.startswith('{build}/')), 'out-of-source build cwd')
        if cwd != '{build}':
            relative(cwd[len('{build}/'):])
        need(type(stage['inputs']) is list and type(stage['outputs']) is list and type(stage['preconditions']) is list, 'explicit stage dependency roles')
        need(stage['preconditions'] and all(type(x) is str and x for x in stage['preconditions']), 'nonempty stage preconditions')
        for role in stage['inputs']:
            require_available(role)
        for value in [cwd] + stage['argv']:
            leftover = TOKEN.sub('', value)
            need('{' not in leftover and '}' not in leftover, 'well-formed placeholders')
            need(not value.startswith('/'), 'no undeclared absolute argument')
            for suffix in re.findall(r'\{build\}([^ :\t]*)', value):
                if suffix:
                    need(suffix.startswith('/'), 'build-root separator')
                    relative(suffix[1:])
            for token in TOKEN.findall(value):
                need(token in ('repo', 'build') or token.startswith('tool:') and token[5:] in tool_ids or token.startswith('artifact:') and token[9:] in artifacts, 'declared placeholder: ' + token)
        for index, token in enumerate(stage['argv'][:-1]):
            if token in ('-o', '--Mdir', '-d', '--output', '--out', '--target-dir'):
                target = stage['argv'][index + 1]
                need(target.startswith('{build}/') or token == '-d' and target == '.', 'declared output remains outside sources')
        available.update(stage['outputs'])
    need(type(fragment['unresolved_prerequisites']) is list and fragment['unresolved_prerequisites'] and all(type(x) is str and x for x in fragment['unresolved_prerequisites']), 'unrun recipe retains unresolved prerequisites')
    encoded = json.dumps(fragment, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    need(hashlib.sha256(encoded).hexdigest() == CONTRACT_DIGESTS.get(fragment['component']), 'exact reviewed fixed description; no caller-provided acceptance digest')
    return fragment


def describe(fragments):
    values = [validate_fragment(value) for value in fragments]
    need(len(values) == len(CONTRACT_DIGESTS) and {value['component'] for value in values} == set(CONTRACT_DIGESTS), 'exactly one of each fixed component')
    stage_ids = [stage['id'] for value in values for stage in value['stages']]
    output_roles = [role for value in values for stage in value['stages'] for role in stage['outputs']]
    need(len(stage_ids) == len(set(stage_ids)) and len(output_roles) == len(set(output_roles)), 'unambiguous cross-component stages and outputs')
    return dict(schema='UNRUN_PORTABLE_NATIVE_BUILD_DESCRIPTION_V1',
                status='SOURCE_DESCRIPTION_ONLY_NO_EXECUTION_AUTHORITY',
                execution_authority=False, portable_build_executed=False,
                components=values,
                unresolved_prerequisites={value['component']: value['unresolved_prerequisites'] for value in values})


def render(fragments):
    """Return token arrays for inspection. Never interpolate or invoke a command."""
    plan = describe(fragments)
    return dict(status=plan['status'], execution_authority=False,
                unresolved_prerequisites=plan['unresolved_prerequisites'],
                stages=[dict(component=value['component'], **stage)
                        for value in plan['components'] for stage in value['stages']])


def checked_bytes(path, row):
    need(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path, 'canonical regular source')
    before = path.stat()
    need(before.st_size <= 8 << 20, 'bounded source input')
    raw = path.read_bytes()
    after = path.stat()
    stamp = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    need(stamp(before) == stamp(after) and hashlib.sha256(raw).hexdigest() == row['sha256'], 'stable exact source buffer')
    if 'bytes' in row:
        need(len(raw) == row['bytes'], 'exact source size')
    return raw


def check_repository_inputs(fragments, root=REPO):
    pins = {}
    for value in describe(fragments)['components']:
        for row in value['inputs']:
            path = row['path']
            need(path not in pins or pins[path] == row['sha256'], 'consistent shared repository input')
            need(relative(path).suffix not in ('.bin', '.so', '.a', '.o', '.class', '.npy', '.npz', '.pt', '.fir'), 'source inputs only')
            checked_bytes(root / path, row)
            pins[path] = row['sha256']
    return len(pins)


def load_fragments():
    catalog = json.loads(checked_bytes(D / 'FRAGMENTS.json', {'sha256': FRAGMENTS_SHA256}))
    need(catalog['schema'] == 'UNRUN_NATIVE_RECIPE_SOURCES_V1', 'recipe source manifest')
    modules, fragments, test_sources = {}, [], []
    for row in catalog['fragments']:
        name = row['module_name']
        need(re.fullmatch('[a-z][a-z0-9_]*', name) and name not in modules, 'unique fragment module')
        source = row['module']
        source_path = D / relative(source['path'])
        raw = checked_bytes(source_path, source)
        module = types.ModuleType(name)
        module.__file__ = str(source_path)
        exec(compile(raw, str(source_path), 'exec', dont_inherit=True, optimize=0), module.__dict__)
        if row.get('catalog'):
            data_row = row['catalog']
            data = json.loads(checked_bytes(D / relative(data_row['path']), data_row))
            module.validate(data)
            fragment = module.describe(data)
            module.validate_description(fragment, data)
        else:
            fragment = module.describe()
            module.validate(fragment)
        need(fragment['component'] == row['component'], 'exact source-to-component role')
        modules[name] = module
        fragments.append(fragment)
        test = row['tests']
        test_path = D / relative(test['path'])
        test_sources.append((str(test_path), checked_bytes(test_path, test)))
    describe(fragments)
    return modules, fragments, test_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--describe', action='store_true', help='print full source descriptions only')
    mode.add_argument('--render', action='store_true', help='print tokenized command templates only')
    mode.add_argument('--check-repository', action='store_true', help='hash declared repository source inputs, without tools or generation')
    args = parser.parse_args()
    _, fragments, _ = load_fragments()
    if args.describe:
        result = describe(fragments)
    elif args.render:
        result = render(fragments)
    else:
        result = dict(status='UNRUN_NATIVE_RECIPE_SOURCE_CHECK_ONLY',
                      execution_authority=False, portable_build_executed=False,
                      components=[value['component'] for value in fragments],
                      stages=sum(len(value['stages']) for value in fragments),
                      unresolved_prerequisites={value['component']: len(value['unresolved_prerequisites']) for value in fragments})
        if args.check_repository:
            result['verified_repository_inputs'] = check_repository_inputs(fragments)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
