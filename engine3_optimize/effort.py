"""Engineering-hours and money model (PRD 3 v0.2). Every number here is an EDITABLE ASSUMPTION.

- Hours per component and per interface, low/base/high.
- Money = hours x editable loaded hourly rate (labor) + non-labor costs (license/purchase/infra/maintenance).
- No staffing, calendar or headcount estimates (explicitly deferred).
- Missing estimates stay None ("unknown"), never 0.
- Interface integration is counted ONLY on interfaces, shared work ONLY once (no double counting).
"""
from __future__ import annotations

from pydantic import BaseModel

from shared.schemas import EffortRange as R


class EffortAssumptions(BaseModel):
    hourly_rate: float = 120.0
    currency: str = "USD"
    build_hours_by_kind: dict[str, R] = {
        "service": R(low=400, base=700, high=1200),
        "ui": R(low=500, base=900, high=1500),
        "client_app": R(low=600, base=1000, high=1800),
        "edge_device": R(low=300, base=600, high=1000),
        "gateway": R(low=300, base=500, high=900),
        "pipeline": R(low=600, base=1100, high=2000),
        "library": R(low=200, base=400, high=700),
    }
    # share of build/adaptation hours added for these activities
    activity_fractions: dict[str, float] = {"configuration": 0.05, "testing": 0.25, "security": 0.10, "deployment": 0.08}
    reuse_onboarding_hours: R = R(low=24, base=40, high=80)
    reuse_estimate_spread: tuple[float, float] = (0.6, 2.0)   # passport adaptation estimate -> low/high multipliers
    reuse_missing_capability_build_factor: float = 0.8       # fraction of BUILD hours per missing capability share
    # Floor for adapting reused software, as a fraction of the BUILD baseline for that component kind.
    # LLM passport estimates are indicative and tend to be optimistic; the floor covers deployment hardening,
    # domain-model mapping, security review of third-party code and long-term ownership onboarding.
    reuse_adaptation_floor: R = R(low=0.15, base=0.25, high=0.40)
    buy_integration_fraction: R = R(low=0.15, base=0.30, high=0.50)  # of BUILD hours
    buy_maintenance_fraction_per_year: float = 0.20          # of acquisition, when price is known
    interface_hours_by_mode: dict[str, R] = {
        "sync": R(low=40, base=80, high=160), "async": R(low=30, base=60, high=120),
        "stream": R(low=60, base=120, high=240), "batch": R(low=30, base=50, high=100),
    }
    third_party_interface_factor: float = 1.5   # data-model conversion when an endpoint is REUSE/BUY
    fictional_device_interface_factor: float = 1.5
    shared_work: dict[str, R] = {
        "Platform, CI/CD and containerization": R(low=160, base=240, high=400),
        "Security hardening and accreditation preparation": R(low=200, base=320, high=600),
        "System integration and end-to-end testing": R(low=240, base=400, high=700),
    }
    risk_reserve_fraction: float = 0.15

    def labor(self, hours: R) -> R:
        return hours.scale(self.hourly_rate)


def with_activities(core: R, a: EffortAssumptions) -> tuple[R, dict[str, R]]:
    breakdown = {"build/adaptation": core}
    total = core
    for k, f in a.activity_fractions.items():
        part = core.scale(f)
        breakdown[k] = part
        total = total + part
    return total, breakdown
