"""Pure-stdlib static graph validation. No readelf, subprocess or native imports.

The graph itself must be SHA-pinned by reviewed admission. Caller must verify
actual file bytes before this structural check and runtime mappings afterward.
"""
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError('runtime ELF closure: ' + message)


def verify_graph(graph, files):
    require(type(graph) is dict and graph.get('schema') == 1, 'graph schema')
    roots, nodes, edges = graph.get('roots'), graph.get('files'), graph.get('edges')
    require(type(roots) is list and roots and len(roots) == len(set(roots)), 'unique nonempty roots')
    require(type(nodes) is dict and type(edges) is list and type(files) is dict, 'graph containers')
    require(graph.get('loader_environment') == {'LD_LIBRARY_PATH': '', 'LD_PRELOAD': ''}, 'reviewed loader policy')
    for path, spec in nodes.items():
        require(type(path) is str and Path(path).is_absolute(), 'absolute node path')
        require(str(Path(path).resolve(strict=True)) == path, 'canonical real node path')
        require(type(spec) is dict and type(spec.get('bytes')) is int and spec['bytes'] > 0, 'node bytes')
        require(type(spec.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', spec['sha256']) is not None, 'node digest')
        require(path in files and type(files[path]) is dict, 'node absent from checked file manifest: ' + path)
        require(all(files[path].get(k) == spec[k] for k in ('bytes', 'sha256')), 'node/file pin mismatch: ' + path)
        require(type(spec.get('needed')) is list and all(type(n) is str and n and '/' not in n for n in spec['needed']), 'SONAME list')
        require(len(spec['needed']) == len(set(spec['needed'])), 'duplicate NEEDED')
    require(all(root in nodes for root in roots), 'root absent from nodes')
    actual = {}; adjacent = {p: [] for p in nodes}
    for edge in edges:
        require(type(edge) is dict and set(edge) == {'from', 'needed', 'link', 'target', 'kind'}, 'edge fields')
        source, target, name, kind = (edge[k] for k in ('from', 'target', 'needed', 'kind'))
        require(source in nodes and target in nodes and target in files, 'edge source/target missing')
        require(kind in ('needed', 'interpreter'), 'edge kind')
        key = (source, kind, name)
        require(key not in actual, 'duplicate or ambiguous dependency edge')
        link = edge['link']
        require(type(link) is str and Path(link).is_absolute(), 'absolute dependency link')
        require(str(Path(link).resolve(strict=True)) == target, 'system/RPATH link changed')
        if kind == 'needed':
            require(Path(link).name == name and nodes[target].get('soname') in (name, None), 'resolved SONAME differs')
        else:
            require(link == name, 'interpreter link differs')
        actual[key] = target; adjacent[source].append(target)
    expected = {(p, 'needed', name) for p, n in nodes.items() for name in n['needed']}
    expected.update((p, 'interpreter', n['interpreter']) for p, n in nodes.items() if n.get('interpreter'))
    require(set(actual) == expected, 'NEEDED/interpreter edge set incomplete or extra')
    reachable = set(); pending = list(roots)
    while pending:
        p = pending.pop()
        if p not in reachable:
            reachable.add(p); pending.extend(adjacent[p])
    require(reachable == set(nodes), 'non-runtime or unreachable library injected')
    return True
