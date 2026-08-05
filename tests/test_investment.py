from __future__ import annotations
import unittest
from genesis.services.investment import InvestmentPolicyError, RegenerativeInvestmentService

class RegenerativeInvestmentTests(unittest.TestCase):
    def setUp(self): self.service = RegenerativeInvestmentService()
    def test_all_distributable_profit_is_split_equally_without_losing_cents(self):
        p=self.service.propose(revenue_cents=100_003,obligations_cents=40_000,reserve_cents=20_000)
        self.assertEqual(p["distributable_profit_cents"],40_003); self.assertEqual(p["allocated_total_cents"],40_003)
        self.assertLessEqual(max(p["allocations_cents"].values())-min(p["allocations_cents"].values()),1); self.assertFalse(p["executable"])
    def test_obligations_and_reserves_cannot_be_invested(self):
        with self.assertRaises(InvestmentPolicyError): self.service.propose(revenue_cents=100,obligations_cents=80,reserve_cents=30)
    def test_metals_require_complete_audited_provenance(self):
        self.assertFalse(self.service.validate_metals_evidence({"ethical_source_verified":True})["eligible"])
        evidence={k:True for k in ("ethical_source_verified","chain_of_custody","independent_audit","investment_grade","counterparty_checked","recycled_or_responsibly_mined")}
        result=self.service.validate_metals_evidence(evidence); self.assertTrue(result["eligible"]); self.assertFalse(result["execution_enabled"])
