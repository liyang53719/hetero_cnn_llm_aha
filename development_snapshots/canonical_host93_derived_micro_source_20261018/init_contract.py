"""Finite known generated-container contract, not a general C++ parser."""
import sys
if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    raise SystemExit('Require -I -S -B before local loading.')
if __name__ == '__main__':
    raise SystemExit('Load only from an explicitly size/SHA checked buffer.')
import hashlib
import re


def require(ok, why):
    if not ok:
        raise ValueError(why)


def lexical_mask(text):
    """Mask only ordinary comments/quoted literals, preserving byte positions."""
    require(text.isascii() and '\x00' not in text and len(text) <= 65536, 'bounded ASCII generated wrapper')
    masked = list(text)
    spans = []
    i = 0
    while i < len(text):
        start = i
        kind = None
        if text.startswith('//', i):
            end = text.find('\n', i + 2)
            i = len(text) if end < 0 else end
            kind = 'line_comment'
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            require(end >= 0, 'unterminated block comment')
            i = end + 2
            kind = 'block_comment'
        elif text[i] in ('"', "'"):
            # Fixed generated output has ordinary literals only. Reject raw/wide
            # prefixes instead of guessing a more general C++ string grammar.
            require(i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_'), 'unsupported literal prefix')
            quote = text[i]
            i += 1
            while i < len(text) and text[i] != quote:
                require(text[i] not in '\r\n', 'newline in ordinary literal')
                if text[i] == '\\':
                    require(i + 1 < len(text) and text[i + 1] not in '\r\n', 'unsupported literal escape')
                    i += 2
                else:
                    i += 1
            require(i < len(text), 'unterminated ordinary literal')
            i += 1
            kind = 'ordinary_literal'
        else:
            i += 1
        if kind is not None:
            spans.append((start, i, kind))
            for pos in range(start, i):
                if masked[pos] not in '\r\n':
                    masked[pos] = ' '
    return ''.join(masked), spans


def initialized_container(raw, leaf):
    require(type(raw) is bytes and len(raw) <= 65536 and
            re.fullmatch(r'micro_leaf[A-Za-z0-9_]*', leaf) is not None, 'fixed tiny leaf wrapper contract')
    text = raw.decode('ascii')
    clean, ignored = lexical_mask(text)
    child = 'V' + leaf
    container = child + '_container'
    declarations = list(re.finditer(r'\bclass\s+' + re.escape(container) + r'\b', clean))
    require(len(declarations) == 1, 'exactly one real target container declaration')
    start = declarations[0].start()
    depth = 0
    for char in clean[:start]:
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            require(depth >= 0, 'invalid pre-container brace scope')
    require(depth == 0, 'target container must be at top-level scope')
    head = re.match(r'class\s+' + re.escape(container) + r'\s*:\s*public\s+' +
                    re.escape(child) + r'\s*\{', clean[start:])
    require(head is not None, 'fixed container inheritance/header')
    pos = start + head.end()
    depth = 1
    while pos < len(clean) and depth:
        depth += (clean[pos] == '{') - (clean[pos] == '}')
        pos += 1
    require(depth == 0, 'unterminated target container')
    end = pos
    while end < len(clean) and clean[end].isspace():
        end += 1
    require(end < len(clean) and clean[end] == ';', 'target container terminator')
    end += 1
    require(not any(a < end and b > start for a, b, _ in ignored), 'unknown comment/literal inside target container')
    block = text[start:end]
    pattern = (r'class\s+' + re.escape(container) + r'\s*:\s*public\s+' + re.escape(child) +
        r'\s*\{\s*public\s*:\s*(?P<field>long\s+long\s+m_seqnum\s*;)\s*' +
        r'(?P<ctor>' + re.escape(container) + r'\s*\(\s*const\s+char\s*\*\s*scopep__V\s*\)\s*:\s*' +
        re.escape(child) + r'\s*\(\s*scopep__V\s*\)\s*,\s*(?P<initializer>m_seqnum\s*\{\s*0\s*\})\s*\{\s*\})\s*\}\s*;')
    found = re.fullmatch(pattern, block)
    require(found is not None, 'target field and sole constructor require exact m_seqnum{0} initializer')
    ranges = {name: [start + found.start(name), start + found.end(name)]
              for name in ('field', 'ctor', 'initializer')}
    require(ranges['ctor'][0] <= ranges['initializer'][0] < ranges['initializer'][1] <= ranges['ctor'][1],
            'initializer must be inside target constructor range')
    return {'status': 'FINITE_TARGET_CONTAINER_INITIALIZER_WITNESS', 'leaf': leaf,
            'container': container, 'class_byte_range': [start, end], 'member_ranges': ranges,
            'class_sha256': hashlib.sha256(raw[start:end]).hexdigest(),
            'wrapper_sha256': hashlib.sha256(raw).hexdigest(), 'initialized_member': 'm_seqnum',
            'initializer_value': 0, 'unknown_body_refused': True,
            'does_not_claim_general_cpp_semantics_or_runtime_correctness': True}
