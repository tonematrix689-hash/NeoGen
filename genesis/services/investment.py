"""Owner-directed regenerative profit mandate and non-executable proposals."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

class InvestmentPolicyError(RuntimeError):
    pass

class RegenerativeInvestmentService:
    pillars = ("renewable_energy", "environmental_restoration", "sustainable_diverse_agriculture", "ethical_precious_metals_and_gems")

    def mandate(self) -> dict[str, Any]:
        return {"profit_allocation_percent": 100, "basis": "distributable_profit_after_taxes_wages_refunds_operating_costs_and_required_reserves", "pillars": {p: 25 for p in self.pillars}, "execution_enabled": False, "approval_required": True, "metals_and_gems_requirements": ["verified ethical source", "recycled supply separately identified", "responsibly mined supply requires traceable due diligence", "investment-grade specification", "independent audit or assurance", "documented chain of custody and counterparty checks"], "notice": "Proposal only. Directors, tax and licensed financial professionals must review before funds move."}

    def propose(self, *, revenue_cents: int, obligations_cents: int, reserve_cents: int) -> dict[str, Any]:
        values = tuple(int(v) for v in (revenue_cents, obligations_cents, reserve_cents))
        if any(v < 0 for v in values): raise InvestmentPolicyError("financial inputs cannot be negative")
        distributable = values[0] - values[1] - values[2]
        if distributable < 0: raise InvestmentPolicyError("there is no distributable profit after obligations and reserves")
        base, remainder = divmod(distributable, len(self.pillars))
        allocations = {p: base + (1 if i < remainder else 0) for i, p in enumerate(self.pillars)}
        return {"revenue_cents": values[0], "obligations_cents": values[1], "required_reserve_cents": values[2], "distributable_profit_cents": distributable, "allocations_cents": allocations, "allocated_total_cents": sum(allocations.values()), "executable": False, "requires_owner_and_professional_review": True, "evidence_required": self.mandate()["metals_and_gems_requirements"], "created_at": datetime.now(timezone.utc).isoformat()}

    def validate_metals_evidence(self, evidence: dict[str, bool]) -> dict[str, Any]:
        required = ("ethical_source_verified", "chain_of_custody", "independent_audit", "investment_grade", "counterparty_checked", "recycled_or_responsibly_mined")
        missing = [field for field in required if evidence.get(field) is not True]
        return {"eligible": not missing, "missing": missing, "execution_enabled": False}

    def stats(self) -> dict[str, int]: return {"pillars": 4, "allocation_percent": 100}
