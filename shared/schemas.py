"""Shared JSON contracts for the three SwissLink engines.

Engine 1 (PRD 1) - software exploration      -> SoftwareCapabilityPassport, CandidateRanking
Engine 2 (PRD 2) - architecture generator    -> ArchitectureDesign, ComponentSearchSpec, ArchitectureFeedback
Engine 3 (PRD 3) - build/buy/reuse optimizer -> ComponentOption, ArchitectureEvaluation, Iteration, Overlay
Shared           - independent LLM judge     -> ValidationReport

Rule used everywhere: an unknown value is None (shown as "unknown"), never 0.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, NonNegativeFloat


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


EvidenceStatus = Literal["verified", "declared", "inferred", "unknown"]
Severity = Literal["critical", "high", "medium", "low", "info"]
Decision = Literal["BUILD", "BUY", "REUSE"]


class EffortRange(BaseModel):
    """Low/base/high range. None means unknown (never treated as zero)."""
    low: Optional[NonNegativeFloat] = None
    base: Optional[NonNegativeFloat] = None
    high: Optional[NonNegativeFloat] = None

    @property
    def known(self) -> bool:
        return self.base is not None

    def __add__(self, other: "EffortRange") -> "EffortRange":
        def add(a, b):
            return None if a is None or b is None else a + b
        return EffortRange(low=add(self.low, other.low), base=add(self.base, other.base), high=add(self.high, other.high))

    def scale(self, k: float) -> "EffortRange":
        f = lambda v: None if v is None else v * k
        return EffortRange(low=f(self.low), base=f(self.base), high=f(self.high))


# ---------------------------------------------------------------------------
# Engine 1 - Software Capability Passport
# Base = software_capability_passport.schema.json (Drive). All its required
# fields are kept verbatim; PRD 1 v0.3 fields are optional extensions.
# ---------------------------------------------------------------------------
class PassportSource(BaseModel):
    repository_url: str = ""
    homepage_url: str = ""


class PassportCapability(BaseModel):
    name: str
    coverage: Literal["full", "partial", "none"]
    notes: str = ""
    # PRD 1 extensions
    capability_id: Optional[str] = None
    evidence_status: EvidenceStatus = "unknown"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    evidence_refs: list[str] = []


class AdaptationEffortHours(BaseModel):
    estimate: NonNegativeFloat
    confidence: Literal["low", "medium", "high"]
    assumptions: list[str] = []


class PassportFit(BaseModel):
    score: Optional[float] = Field(default=None, ge=0, le=100)
    hard_requirements_met: Optional[bool] = None
    gaps: list[str] = []


class PassportEvidence(BaseModel):
    claim: str
    source_ref: str
    verified: bool = False


class PassportValidation(BaseModel):
    status: Literal["pending", "passed", "failed"] = "pending"
    judge_notes: str = ""


class InterfaceDetail(BaseModel):
    name: str
    protocol: str = "unknown"
    direction: Literal["in", "out", "bidirectional", "unknown"] = "unknown"
    schema_ref: str = ""
    evidence_status: EvidenceStatus = "unknown"


class CostInputs(BaseModel):
    license_pricing_known: bool = False
    license_pricing_note: str = "unknown"
    adaptation_assumptions: list[str] = []


class SoftwareCapabilityPassport(BaseModel):
    # --- Drive schema (required) ---
    passport_id: str
    software_name: str
    version: str = "unknown"
    source: PassportSource
    capabilities: list[PassportCapability]
    interfaces: list[str]
    dependencies: list[str] = []
    license: str
    maturity: Literal["experimental", "developing", "stable", "unknown"]
    constraints: list[str] = []
    adaptation_effort_hours: AdaptationEffortHours
    fit: PassportFit = PassportFit()
    evidence: list[PassportEvidence]
    validation: PassportValidation
    # --- PRD 1 v0.3 extensions (optional) ---
    revision: Optional[str] = None
    description: str = ""
    interfaces_detail: list[InterfaceDetail] = []
    deployment_constraints: list[str] = []
    runtime: list[str] = []
    tests_present: Optional[bool] = None
    known_gaps: list[str] = []
    risks: list[str] = []
    cost_inputs: CostInputs = CostInputs()
    is_custom_development: bool = False
    analysis_timestamp: str = Field(default_factory=now_iso)
    stars: Optional[int] = None
    last_activity: Optional[str] = None


# Alias kept for PRD 1 naming
CandidatePassport = SoftwareCapabilityPassport


class CandidateRanking(BaseModel):
    """Engine 1 ranks component fit only. Engine 3 alone chooses Build/Buy/Reuse."""
    component_id: str
    candidate_id: str
    eligible: bool
    exclusion_reasons: list[str] = []
    dimension_scores: dict[str, Optional[float]] = {}   # 0..1, None = unknown
    weights: dict[str, float] = {}
    total_score: Optional[float] = None                 # 0..100, eligible only
    rank: Optional[int] = None
    covered_capabilities: list[str] = []
    missing_capabilities: list[str] = []
    required_modifications: list[str] = []
    explanation: str = ""
    confidence: Literal["low", "medium", "high"] = "low"


# ---------------------------------------------------------------------------
# Engine 2 - Architecture
# ---------------------------------------------------------------------------
class Requirement(BaseModel):
    id: str
    text: str
    kind: Literal["functional", "nonfunctional", "interface", "constraint"]
    priority: Literal["mandatory", "desirable", "optional"]
    status: Literal["explicit", "inferred"]
    source_passage: str = ""
    ambiguity: Optional[str] = None


class OpenQuestion(BaseModel):
    id: str
    question: str
    requirement_ids: list[str] = []
    kind: Literal["missing_value", "ambiguity", "contradiction", "scope"] = "ambiguity"


class Capability(BaseModel):
    id: str
    name: str
    level: Literal["domain", "capability", "operation"]
    parent_id: Optional[str] = None
    description: str = ""
    requirement_ids: list[str] = []


class Component(BaseModel):
    id: str
    name: str
    kind: Literal["service", "ui", "edge_device", "gateway", "pipeline", "library", "client_app"] = "service"
    subsystem: str = ""
    trust_zone: str = ""
    purpose: str = ""
    required_capabilities: list[str] = []
    optional_capabilities: list[str] = []
    responsibilities: list[str] = []
    inputs: list[str] = []
    outputs: list[str] = []
    data_owned: list[str] = []
    dependencies: list[str] = []
    runtime_assumptions: list[str] = []
    deployment_assumptions: list[str] = []
    quality_constraints: list[str] = []
    integration_requirements: list[str] = []
    requirement_ids: list[str] = []
    design_assumptions: list[str] = []


class Interface(BaseModel):
    id: str
    source: str
    target: str
    name: str
    payload: str = ""
    protocol_candidates: list[str] = []
    mode: Literal["sync", "async", "stream", "batch"] = "async"
    error_handling: str = ""
    security: str = ""
    requirement_ids: list[str] = []


class DataStore(BaseModel):
    id: str
    name: str
    owner_component: str
    contents: str = ""
    kind: str = ""


class ExternalSystem(BaseModel):
    id: str
    name: str
    description: str = ""
    fictional: bool = False


class CoverageEntry(BaseModel):
    requirement_id: str
    component_ids: list[str] = []
    status: Literal["covered", "gap"]
    note: str = ""


class ValidationFinding(BaseModel):
    id: str
    severity: Severity
    rule: str
    message: str
    refs: list[str] = []


class ChangeLogEntry(BaseModel):
    version: int
    summary: str
    reason: str = ""
    added: list[str] = []
    removed: list[str] = []
    modified: list[str] = []
    feedback_id: Optional[str] = None
    timestamp: str = Field(default_factory=now_iso)


class ArchitectureDesign(BaseModel):
    architecture_id: str
    version: int = 1
    parent_id: Optional[str] = None
    title: str = ""
    source_name: str = ""          # SRS file name
    generated_with: str = ""       # model used by Engine 2
    requirements_revision: str = ""
    requirements: list[Requirement] = []
    open_questions: list[OpenQuestion] = []
    capabilities: list[Capability] = []
    components: list[Component] = []
    interfaces: list[Interface] = []
    data_stores: list[DataStore] = []
    external_systems: list[ExternalSystem] = []
    assumptions: list[str] = []
    risks: list[str] = []
    coverage: list[CoverageEntry] = []
    validation_findings: list[ValidationFinding] = []
    mermaid_source: str = ""
    design_rationale: str = ""
    constraints: list[str] = []
    change_log: list[ChangeLogEntry] = []
    created_at: str = Field(default_factory=now_iso)

    @property
    def key(self) -> str:
        return f"{self.architecture_id}@v{self.version}"


class ComponentSearchSpec(BaseModel):
    component_id: str
    name: str
    purpose: str = ""
    required_capabilities: list[str] = []
    optional_capabilities: list[str] = []
    capability_names: dict[str, str] = {}
    interfaces_required: list[str] = []
    data_constraints: list[str] = []
    runtime_constraints: list[str] = []
    security_constraints: list[str] = []
    requirement_ids: list[str] = []
    acceptance_criteria: list[str] = []
    search_terms: list[str] = []


class ArchitectureFeedback(BaseModel):
    feedback_id: str
    source: Literal["PRD3"] = "PRD3"
    component_ids: list[str] = []
    observations: list[str] = []
    changed_constraints: list[str] = []
    requested_change: str
    priority: Literal["low", "medium", "high"] = "medium"


# ---------------------------------------------------------------------------
# Engine 3 - Optimization
# ---------------------------------------------------------------------------
class NonLaborCost(BaseModel):
    label: str
    one_time: EffortRange = EffortRange()
    recurring_per_year: EffortRange = EffortRange()
    known: bool = False
    note: str = ""


class EffortEstimate(BaseModel):
    target_id: str                      # component or interface id (stable Engine 2 id)
    target_kind: Literal["component", "interface", "shared"]
    hours: EffortRange
    breakdown: dict[str, EffortRange] = {}   # build, adaptation, configuration, integration, testing, security, deployment
    confidence: Literal["low", "medium", "high"] = "low"
    source: str = ""
    assumptions: list[str] = []


class ComponentOption(BaseModel):
    architecture_id: str
    component_id: str
    candidate_id: Optional[str] = None
    candidate_name: str = ""
    decision: Decision
    coverage: list[str] = []
    gaps: list[str] = []
    interface_fit: Optional[float] = None
    adaptation_effort_range: EffortRange = EffortRange()
    effort: Optional[EffortEstimate] = None
    nonlabor_costs: list[NonLaborCost] = []
    offline_capable: Optional[bool] = None
    license: str = "unknown"
    evidence_refs: list[str] = []
    assumptions: list[str] = []
    rationale: str = ""


class ArchitectureEvaluation(BaseModel):
    architecture_id: str
    architecture_version: int
    label: str = ""
    strategy: str = ""
    component_options: list[ComponentOption] = []
    interface_efforts: list[EffortEstimate] = []
    mandatory_coverage: Optional[float] = None
    integration_effort_range: EffortRange = EffortRange()
    development_effort_range: EffortRange = EffortRange()
    verification_effort_range: EffortRange = EffortRange()
    total_hours: EffortRange = EffortRange()
    hourly_rate: float = 0.0
    labor_cost_range: EffortRange = EffortRange()
    acquisition_cost_range: EffortRange = EffortRange()
    lifecycle_cost_range: EffortRange = EffortRange()
    unknown_estimates: list[str] = []
    risks: list[str] = []
    unresolved_gaps: list[str] = []
    hard_gate_violations: list[str] = []
    feasible: bool = True
    pareto: bool = False
    score_breakdown: dict[str, Optional[float]] = {}


class OverlayValue(BaseModel):
    hours: EffortRange = EffortRange()
    money: EffortRange = EffortRange()
    decision: Optional[Decision] = None
    label: str = ""


class Overlay(BaseModel):
    """Engine 3 overlay keyed by Engine 2's stable node / edge ids."""
    architecture_id: str
    architecture_version: int
    nodes: dict[str, OverlayValue] = {}
    edges: dict[str, OverlayValue] = {}
    total_hours: EffortRange = EffortRange()
    total_money: EffortRange = EffortRange()
    hourly_rate: float = 0.0


class Iteration(BaseModel):
    iteration_id: str
    parent_iteration_id: Optional[str] = None
    user_instruction: str = ""
    constraints: list[str] = []
    objectives: list[str] = []
    proposals: list[str] = []            # architecture keys "id@vN"
    evaluations: list[ArchitectureEvaluation] = []
    critique: list[str] = []
    changes: list[str] = []
    explanation: str = ""
    timestamp: str = Field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Shared independent validation
# ---------------------------------------------------------------------------
class JudgeFinding(BaseModel):
    severity: Severity
    claim: str
    problem: str
    evidence: str = ""
    suggested_fix: str = ""


class ValidationReport(BaseModel):
    target_kind: Literal["passport", "ranking", "architecture", "evaluation"]
    target_id: str
    verdict: Literal["PASS", "REVISE", "BLOCK"]
    findings: list[JudgeFinding] = []
    deterministic_checks: list[str] = []
    rubric: str = ""
    model: str = ""
    timestamp: str = Field(default_factory=now_iso)
