"""Control-only regression: real coordinator AST plus explicitly synthetic driver.
No arithmetic, native import/build, tensor execution, or acceptance evidence.
"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from candidates.qwen35_gdn_prefill.test_full_driver_progress_cold import F, TickDouble, Clock

class BudgetAbortReceiptTests(unittest.TestCase):
    def test_budget_abort_preserves_owner_reason_and_committed_generation(self):
        c = TickDouble()
        c.phase, c.role = 'carried128', 'o'
        c.roots = F.CommittedRoots(1, 10, 20, 30)
        saved_roots = c.roots
        c.observe = None
        c.active.job.tag = 25
        c.commands = [{'owner_tag': i, 'terminal_status': None} for i in range(1, 25)]
        reason = 'local reset requires coordinated backend reset'
        calls = []
        def synthetic_driver_tick(**controls):
            calls.append(controls)
            self.assertTrue(controls['abort'])
            c.active.response = (25, reason, 0)
            return {'response_fire': True}
        c.active.tick = synthetic_driver_tick
        with patch.object(F, 'time', Clock([0., 1.]), create=True):
            result = c.run_window('carried128', cold=False, expected_generation=1, budget_seconds=1)
        self.assertEqual(result.status, reason)
        self.assertEqual(result.failed_role, 'o')
        self.assertEqual(result.generation, 1)
        self.assertIs(c.roots, saved_roots)
        self.assertTrue(c.locked)
        self.assertEqual(len(c.commands), 25)
        self.assertFalse(c.commands[-1]['block_committed'])
        self.assertEqual(c.commands[-1]['terminal_status'], reason)
        self.assertFalse(any(r.published for r in c.memory.regions.values()))
        self.assertNotIn('joint_commit', c.events)
        self.assertEqual(len(calls), 1)

if __name__ == '__main__':
    unittest.main()
