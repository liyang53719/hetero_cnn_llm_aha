"""Explicit independent QKV recipe; no official result or activation access."""
import ctypes
import hashlib
import json
from pathlib import Path

from . import kernel

PROFILE = 'qwen2-independent-qkv-block-pair-v1'
SOURCE = 'candidates/qwen2_resident_matrix/raw_kv_native_qkv/adapter.py'
IMPORTED_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
ROLES = {'self_attn.q_proj': 1536, 'self_attn.k_proj': 256, 'self_attn.v_proj': 256}


def need(ok):
    if not ok:
        raise ValueError('independent QKV recipe contract')


class Recipe:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.receipt = kernel.verify(self.directory)
        need(self.receipt['source_sha256'].get(SOURCE) == IMPORTED_SHA256)
        self.library = ctypes.CDLL(str(self.receipt['library_path']))
        self.function = self.library.qkv_pair
        pointer = ctypes.POINTER(ctypes.c_float)
        self.function.argtypes = [ctypes.c_int, ctypes.c_int, pointer, pointer, pointer, pointer]
        self.function.restype = ctypes.c_int
        self.revalidate()

    def revalidate(self):
        need(kernel.verify(self.directory) == self.receipt and
             self.receipt['source_sha256'].get(SOURCE) == IMPORTED_SHA256)

    def identity(self):
        self.revalidate()
        return dict(profile=PROFILE, library_sha256=self.receipt['library_sha256'],
                    source_sha256=json.loads(json.dumps(self.receipt['source_sha256'])), pins_sha256=self.receipt['pins_sha256'])

    def linear(self, value, weight, bias, role):
        """Own decoded BF16 inputs only; weight transpose is a lossless copy."""
        import numpy as np
        self.revalidate()
        need(type(role) is str and role in ROLES)
        columns = ROLES[role]
        need(type(value) is np.ndarray and value.dtype == np.dtype('float32') and
             value.ndim == 3 and value.shape[0] == 1 and value.shape[1] in (16, 128) and value.shape[2] == 1536)
        need(type(weight) is np.ndarray and weight.dtype == np.dtype('float32') and weight.shape == (columns, 1536))
        need(type(bias) is np.ndarray and bias.dtype == np.dtype('float32') and bias.shape == (columns,))
        for item in (value, weight, bias):
            need(bool(np.isfinite(item).all()) and bool(((item.view(np.uint32) & 0xffff) == 0).all()))
        activation = np.array(value, dtype=np.float32, order='C', copy=True)
        weights = np.array(weight.T, dtype=np.float32, order='C', copy=True)
        biases = np.array(bias, dtype=np.float32, order='C', copy=True)
        output = np.empty((1, value.shape[1], columns), dtype=np.float32)
        pointer = ctypes.POINTER(ctypes.c_float)
        code = self.function(value.shape[1], columns,
                             *(item.ctypes.data_as(pointer) for item in (activation, weights, biases, output)))
        need(type(code) is int and code == 0)
        need(bool(np.isfinite(output).all()) and bool(((output.view(np.uint32) & 0xffff) == 0).all()))
        self.revalidate()
        return output


def validate(recipe, *, tokens, carried, threads):
    need(type(recipe) is Recipe and type(tokens) is int and tokens in (16, 128) and
         type(carried) is bool and carried is False and type(threads) is int and threads == 4)
    recipe.revalidate()
    return recipe.identity()
