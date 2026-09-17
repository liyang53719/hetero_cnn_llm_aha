"""Strict integer checks for the existing ABI; never coerce floats or booleans.

Explicit one-bit boolean controls are the only exception. Legal integer enum
codes and Integral scalars are canonicalized without changing their wire bits.
"""
from __future__ import annotations

from enum import IntEnum
from numbers import Integral
from typing import TypeVar

E = TypeVar("E", bound=IntEnum)


def integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer (not bool/float/coercible object)")
    return int(value)


def uint(value: object, bits: int, name: str) -> int:
    result = integer(value, name)
    if not 0 <= result < (1 << bits):
        raise ValueError(f"{name} does not fit in {bits} bits")
    return result


def sint(value: object, bits: int, name: str) -> int:
    result = integer(value, name)
    if not -(1 << (bits - 1)) <= result < (1 << (bits - 1)):
        raise ValueError(f"{name} does not fit in signed {bits} bits")
    return result


def enum_value(value: object, enum: type[E], name: str) -> E:
    if isinstance(value, IntEnum) and not isinstance(value, enum):
        raise ValueError(f"{name} belongs to a different enum")
    code = integer(value, name)
    try:
        return enum(code)
    except ValueError as exc:
        raise ValueError(f"{name} has an unknown/reserved enum code: {code}") from exc


def bit(value: object, name: str) -> bool:
    if type(value) is bool:
        return value
    return bool(uint(value, 1, name))


def word_bytes(payload: object, name: str) -> bytes:
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise ValueError(f"{name} must be a 16-byte buffer")
    view = memoryview(payload)
    if not view.contiguous or view.nbytes != 16:
        raise ValueError(f"{name} must contain exactly 16 contiguous bytes")
    return view.tobytes()
