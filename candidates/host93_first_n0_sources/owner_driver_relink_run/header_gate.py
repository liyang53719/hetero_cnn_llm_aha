"""One fixed generated owner header; original checked reader, no parser projection."""
from pathlib import Path

HEADER_NAME = 'obj/VQwenOwnerKernel___024root.h'
HEADER_PIN = {'bytes': 4630258, 'sha256': 'a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf'}
HEADER_CAP = 16 * 1024**2


def header_text(g, tree):
    row = tree['entries'].get(HEADER_NAME)
    g.need(type(row) is dict and row.get('kind') == 'regular' and
           row.get('mode') == '0o600' and
           {key: row.get(key) for key in HEADER_PIN} == HEADER_PIN and
           0 < HEADER_PIN['bytes'] <= HEADER_CAP,
           'OWNER_FIXED_HEADER_IDENTITY')
    raw = g.checked(Path(tree['root']) / HEADER_NAME, HEADER_PIN, HEADER_CAP,
                    fixed_leaf='VQwenOwnerKernel___024root.h')
    # The original identity reader verifies and returns the very buffer consumed here.
    return raw.decode('ascii')
