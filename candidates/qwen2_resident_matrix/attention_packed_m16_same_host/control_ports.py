"""Exact source-only removal of one unused pure non-admission observation."""
import ast
import hashlib

TARGET = 'candidates/qwen2_resident_matrix/ffn_public/execute_numeric.py'
BASELINE_SHA256 = 'd794c0b60b764e378c03fd74436d74e654964a4984efd1f2cedb5f3187724886'
CANDIDATE_SHA256 = 'cf65f59f2af70a2b7b360bf2271bacbdbaeeb3f91c65fcb2c2faf427158ff9d7'
OLD = "        ports = self.ports()\n        before_reset = self.reset_required()\n        before_clock = self.owner.clock\n"
NEW = "        ports = self.ports() if 'job' in inputs else None\n        before_reset = self.reset_required()\n        before_clock = self.owner.clock\n"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def method(tree):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PublicExecution')
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'ordinary_edge')

def transform_bytes(raw):
    """Return the unique candidate only for exact previously executed source."""
    if sha(raw) != BASELINE_SHA256:
        raise ValueError('exact executed composed source required')
    text = raw.decode()
    require(text.count(OLD) == 1, 'ambiguous or missing old statement')
    candidate = text.replace(OLD, NEW).encode()
    require(candidate.decode().replace(NEW, OLD) == text, 'inverse transformation failed')
    before, after = ast.parse(text), ast.parse(candidate)
    bmethod, amethod = method(before), method(after)
    bassign, aassign = bmethod.body[1], amethod.body[1]
    require(isinstance(bassign, ast.Assign) and isinstance(aassign.value, ast.IfExp), 'unexpected assignment AST')
    require(ast.dump(aassign.value.body) == ast.dump(bassign.value), 'original call AST changed')
    amethod.body[1] = bassign
    require(ast.dump(before) == ast.dump(after), 'AST change outside conditional unused read')
    require(sha(candidate) == CANDIDATE_SHA256, 'candidate source identity differs')
    return candidate

# Reusable integration API. It reads no files and imports no target modules.
transform = transform_bytes

