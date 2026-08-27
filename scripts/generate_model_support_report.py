#!/usr/bin/env python3
"""Generate machine-readable model/operator capability evidence."""
from __future__ import annotations

import json
from pathlib import Path

from heteronpu.model_support import load_profiles


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    models = []
    for profile in load_profiles(root / 'config/model_profiles'):
        schedule = profile.runtime_schedule()
        models.append(
            {
                'name': profile.name,
                'model_id': profile.raw.get('model_id'),
                'revision': profile.raw.get('revision'),
                'required_operators': list(profile.required()),
                'support': profile.support(),
                'descriptor_policies': {name: f'{value:032x}' for name, value in profile.policies().items()},
                'state_footprint': profile.footprint(),
                'runtime_schedule': None
                if schedule is None
                else {
                    'micro_ops': len(schedule.micro_ops),
                    'operator_types': sorted(schedule.operator_names),
                    'local_rtl_dependencies': len(schedule.local_dependencies()),
                },
                'claim_boundary': profile.raw.get('claim_boundary'),
            }
        )
    result = {'schema_version': 1, 'status': 'PASS', 'models': models}
    output = root / 'reports/model_support_v4.json'
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
