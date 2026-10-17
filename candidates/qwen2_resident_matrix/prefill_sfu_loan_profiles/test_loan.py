import unittest
from loan import LoanContract,Profile,Request,ContractError

class Tests(unittest.TestCase):
    def make(self,profile=Profile.PRODUCTION_PRIVATE):return LoanContract(profile)
    def tick(self,m,**signals):return m.tick(m.edge+1,**signals)
    def accept(self,m,mode='silu'):
        out=self.tick(m,request=Request(1,mode),ordinary_idle=True,vector_request_ready=True)
        self.assertTrue(out['request_fire'])
    def finish_division(self,m):
        self.tick(m,divider_accept_mask=0xffff)
        self.tick(m,divider_pulse_mask=0x00ff)
        self.tick(m,divider_pulse_mask=0xff00)
    def test_explicit_profiles_and_no_primitive_interface(self):
        with self.assertRaises(ContractError):LoanContract('true')
        m=self.make()
        with self.assertRaises(AttributeError):m.profile=Profile.LEGACY_HELD
        for profile in Profile:
            for request in (Request(1,'div'),Request(1,'exp'),Request(1,lane_count=6)):
                with self.assertRaises(ContractError):self.tick(self.make(profile),request=request)
        with self.assertRaises(ContractError):self.tick(self.make(Profile.LEGACY_HELD),request=Request(1,'binary_add'))
    def test_no_default_ready_or_supply(self):
        m=self.make();self.assertFalse(self.tick(m,request=Request(1))['request_fire'])
        self.assertFalse(self.tick(m,request=Request(1),ordinary_idle=True)['request_fire'])
        self.assertTrue(self.tick(m,request=Request(1),ordinary_idle=True,vector_request_ready=True)['request_fire'])
    def test_abort_rejects_new_request_atomically(self):
        for profile in Profile:
            m=self.make(profile);out=self.tick(m,request=Request(1),ordinary_idle=True,vector_request_ready=True,abort=True)
            self.assertFalse(out['request_fire']);self.assertTrue(out['drained_post']);self.assertTrue(out['reset_required_post'])
    def test_production_abort_waits_and_privately_drains(self):
        m=self.make();self.accept(m)
        out=self.tick(m,abort=True);self.assertFalse(out['drained_post'])
        # An already accepted SiLU may reach division after wrapper abort.
        self.finish_division(m)
        out=self.tick(m,vector_result_valid=True,result_token=10)
        self.assertFalse(out['external_result_valid']);self.assertFalse(out['external_result_fire'])
        self.assertTrue(out['internal_vector_result_fire']);self.assertTrue(out['private_drain'])
        self.assertTrue(out['drained_post']);self.assertFalse(out['publication_allowed'])
    def test_true_vs_false_same_abort_result_signals(self):
        for profile in Profile:
            m=self.make(profile);self.accept(m);self.finish_division(m)
            out=self.tick(m,vector_result_valid=True,result_token=10,abort=True)
            self.assertEqual(out['external_result_valid'],profile is Profile.LEGACY_HELD)
            self.assertEqual(out['private_drain'],profile is Profile.PRODUCTION_PRIVATE)
            self.assertEqual(out['drained_post'],profile is Profile.PRODUCTION_PRIVATE)
            self.assertFalse(out['publication_allowed'])
            if profile is Profile.LEGACY_HELD:
                out=self.tick(m,vector_result_valid=True,result_token=10,external_result_ready=True)
                self.assertTrue(out['external_result_fire']);self.assertFalse(out['publication_allowed'])
    def test_production_held_result_abort_private_without_external_ack(self):
        m=self.make();self.accept(m);self.finish_division(m)
        out=self.tick(m,vector_result_valid=True,result_token=10)
        self.assertTrue(out['external_result_valid']);self.assertFalse(out['drained_post'])
        out=self.tick(m,vector_result_valid=True,result_token=10,abort=True)
        self.assertTrue(out['private_drain']);self.assertTrue(out['drained_post'])
    def test_abort_ready_same_edge_never_exposes_success(self):
        for profile in Profile:
            m=self.make(profile);self.accept(m);self.finish_division(m)
            out=self.tick(m,vector_result_valid=True,result_token=10,external_result_ready=True,abort=True)
            self.assertFalse(out['publication_allowed']);self.assertTrue(out['drained_post'])
            self.assertEqual(out['external_result_fire'],profile is Profile.LEGACY_HELD)
    def test_mode_requires_canonical_string_atomically(self):
        class PretendSilu:
            def __eq__(self, other):return other=='silu'
        class StringSubclass(str):pass
        for mode in (PretendSilu(), StringSubclass('silu'), True, None, 1):
            m=self.make()
            before=dict(m.__dict__)
            with self.assertRaises(ContractError):
                self.tick(m,request=Request(1,mode),ordinary_idle=True,vector_request_ready=True)
            self.assertEqual(m.__dict__,before)
    def test_binary_add_uses_existing_true_profile_no_division(self):
        m=self.make();self.accept(m,'binary_add')
        with self.assertRaises(ContractError):self.tick(m,divider_accept_mask=0xffff)
        out=self.tick(m,vector_result_valid=True,result_token=10,external_result_ready=True)
        self.assertTrue(out['publication_allowed']);self.assertTrue(out['drained_post'])
    def test_pulses_reserved_and_cannot_drop_or_duplicate(self):
        m=self.make();self.accept(m)
        with self.assertRaises(ContractError):self.tick(m,divider_pulse_mask=1)
        self.tick(m,divider_accept_mask=0xffff)
        self.tick(m,divider_pulse_mask=1)
        with self.assertRaises(ContractError):self.tick(m,divider_pulse_mask=1)
        with self.assertRaises(ContractError):self.tick(m,vector_result_valid=True,result_token=10)
        self.tick(m,divider_pulse_mask=0xfffe)
        out=self.tick(m,vector_result_valid=True,result_token=10,external_result_ready=True)
        self.assertTrue(out['publication_allowed'])
    def test_early_error_without_division_still_retires_and_poisons(self):
        for profile in Profile:
            m=self.make(profile);self.accept(m)
            out=self.tick(m,vector_result_valid=True,result_token=10,result_error=True,external_result_ready=True)
            self.assertTrue(out['drained_post']);self.assertTrue(out['reset_required_post']);self.assertFalse(out['publication_allowed'])
    def test_result_held_identity_stable_and_no_same_edge_reaccept(self):
        m=self.make();self.accept(m,'binary_add');self.tick(m,vector_result_valid=True,result_token=10)
        with self.assertRaises(ContractError):self.tick(m,vector_result_valid=True,result_token=11)
        out=self.tick(m,request=Request(2,'binary_add'),ordinary_idle=True,vector_request_ready=True,
                      vector_result_valid=True,result_token=10,external_result_ready=True)
        self.assertFalse(out['request_fire']);self.assertTrue(out['drained_post'])
        out=self.tick(m,request=Request(2,'binary_add'),ordinary_idle=True,vector_request_ready=True)
        self.assertTrue(out['request_fire'])
    def test_poison_blocks_future_request_and_profiles_do_not_mix(self):
        m=self.make();self.accept(m,'binary_add');self.tick(m,abort=True)
        self.tick(m,vector_result_valid=True,result_token=10)
        out=self.tick(m,request=Request(2,'binary_add'),ordinary_idle=True,vector_request_ready=True)
        self.assertFalse(out['request_fire']);self.assertTrue(out['reset_required_pre'])
        for profile in Profile:
            r=self.make(profile).report();self.assertEqual(r['profile'],profile.value)
            self.assertFalse(r['rtl_measured']);self.assertFalse(r['accepted_80']);self.assertFalse(r['accepted_90'])
            self.assertNotIn('wall_cycles',r)

if __name__=='__main__':unittest.main()
