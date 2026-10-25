"""No launch authority: return the frozen M128 draft after exact identity checks."""
import json
from pathlib import Path
from gate_common import file_id, need


def prepare(draft_path, expected_sha256):
    path = Path(draft_path)
    need(file_id(path)['sha256'] == expected_sha256, 'exact draft hash mismatch')
    draft = json.loads(path.read_text())
    need(draft['launch_ready'] is False, 'this helper only reads an unapproved draft')
    need(draft['action'] == 'single_official_m128_full_layer_reference_pair', 'wrong geometry/action')
    return draft
