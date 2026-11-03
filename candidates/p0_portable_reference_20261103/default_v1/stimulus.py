"""New external-boundary inputs. No model, weights, RNG library or arithmetic oracle."""
import hashlib
import json
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def bf16_bytes(width, seed):
    require(width in (1024, 1536, 2048), "unsupported full hidden width")
    require(type(seed) is int and 0 < seed <= 0xffffffff, "seed")
    state = seed
    out = bytearray()
    for index in range(128 * width):
        state ^= (state << 13) & 0xffffffff
        state ^= state >> 17
        state ^= (state << 5) & 0xffffffff
        state &= 0xffffffff
        value = 0 if index % 257 == 0 else (((state >> 31) & 1) << 15) | ((119 + ((state >> 8) % 5)) << 7) | (state & 127)
        out.extend(value.to_bytes(2, "little"))
    return bytes(out)


def storage_bytes(raw, dtype):
    require(len(raw) % 2 == 0, "BF16 byte count")
    require(dtype in ("BF16", "FP32"), "storage dtype")
    return raw if dtype == "BF16" else b"".join(b"\x00\x00" + raw[i:i+2] for i in range(0, len(raw), 2))


def emit(profile, output):
    output = Path(output)
    output.mkdir(exist_ok=False)
    raw = bf16_bytes(profile["width"], profile["seed"])
    stored = storage_bytes(raw, profile["storage"])
    records = {}
    for name, data in (("hidden.bf16.bin", raw), ("hidden.storage.bin", stored)):
        with (output / name).open("xb") as stream:
            stream.write(data)
        records[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    manifest = dict(status="GENERATED_INPUT_ONLY_NOT_REFERENCE_OR_DUT", profile=profile["profile"],
                    shape=[1, 128, profile["width"]], model_input_dtype="BF16", storage_dtype=profile["storage"],
                    seed=profile["seed"], files=records,
                    identity="NEW_DETERMINISTIC_EXTERNAL_BLOCK_BOUNDARY_NOT_EMBEDDING_OR_UPSTREAM_PREFIX")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
