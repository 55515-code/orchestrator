"""
Decentralized Governance Substrate Components

Synthesizes patterns from:
- Dignity Stack (commons-governed, horizontally federated AI governance)
- Liberation Stack (decentralization, universal care, non-domination)
- consensuscode (horizontal agent collective, true consensus)
- coop-kernel (democratic software cooperative, algorithmic fairness)
- InterCooperative Network (constraint engine, cooperative contracts, meaning firewall)
- Indigenous decolonial practices (CARE principles, relational accountability)
- Fediverse governance (covenantal federalism, federated diplomacy)
- Open-source governance (commons-based peer production)

All components enforce:
- Decentralization over concentration
- Collective awareness over isolated decision-making
- Non-Westernized perspectives (Indigenous data sovereignty integrated)
- Consensus-driven data (lazy consensus + true consensus mechanisms)
- Sustainable progress (ecological budget constraints, mutual credit)
- Transparent value systems (audit-ready protocols, open formulas)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal

# ------------------------------------------------------------------
# Pattern A: Dignity Stack — Six-Layer Governance Overlay
# ------------------------------------------------------------------

DIGNITY_LAYER_DEPENDENCIES: dict[int, list[int]] = {
    1: [],          # D1 Material independence — foundational
    2: [1],         # D2 Data sovereignty requires D1
    3: [2],         # D3 Contextual integrity requires D2
    4: [2],         # D4 Fiduciary requires D2 (substitutable infrastructure)
    5: [3],         # D5 Participatory governance requires D3
    6: [1, 5],      # D6 Economic justice requires D1 and D5
}

@dataclass(slots=True, frozen=True)
class DignityStackLayer:
    """Single layer of the Dignity Stack governance overlay."""
    layer_index: int  # 1-6
    dimension: str    # governance dimension mapped to layer
    protocol_family: str  # organizational protocol drawn from commons traditions
    verification_predicate: str
    dependency_layer_indices: list[int] = field(default_factory=list)

    def verify_dependencies(self, active_layers: set[int]) -> bool:
        required = set(DIGNITY_LAYER_DEPENDENCIES.get(self.layer_index, []))
        return required.issubset(active_layers)

    def formal_capture_defeat_check(self, capital_governance_decoupled: bool) -> bool:
        """Formal capture defeated when capital does not determine governance rights."""
        return capital_governance_decoupled

DIGNITY_STACK_LAYERS = [
    DignityStackLayer(
        layer_index=1,
        dimension="technological_oversight",
        protocol_family="community_owned_infrastructure_assembly",
        verification_predicate="polycentric_supply_substitutable",
        dependency_layer_indices=[],
    ),
    DignityStackLayer(
        layer_index=2,
        dimension="data_sovereignty",
        protocol_family="ostromian_cooperative_data_trust",
        verification_predicate="unconditional_exit_open_protocols_self_governance",
        dependency_layer_indices=[1],
    ),
    DignityStackLayer(
        layer_index=3,
        dimension="contextual_integrity",
        protocol_family="kropotkin_mutual_aid_federation",
        verification_predicate="federated_context_protocols_structural_boundary_enforcement",
        dependency_layer_indices=[2],
    ),
    DignityStackLayer(
        layer_index=4,
        dimension="fiduciary_automation_limits",
        protocol_family="malatesta_voluntary_fiduciary",
        verification_predicate="revocable_service_federation_reputation_substitutability",
        dependency_layer_indices=[2],
    ),
    DignityStackLayer(
        layer_index=5,
        dimension="participatory_governance",
        protocol_family="bookchin_bakunin_libertarian_municipalism",
        verification_predicate="nested_assemblies_mandated_recallable_delegation",
        dependency_layer_indices=[3],
    ),
    DignityStackLayer(
        layer_index=6,
        dimension="economic_justice",
        protocol_family="proudhonian_mutualism",
        verification_predicate="democratic_surplus_mutual_credit_system",
        dependency_layer_indices=[1, 5],
    ),
]


# ------------------------------------------------------------------
# Pattern B: Capital-Governance Decoupling Enforcement
# ------------------------------------------------------------------

@dataclass(slots=True)
class GovernanceVoteRecord:
    member_id: str
    proposal_id: str
    vote: Literal["approve", "reject", "abstain", "block"]
    weight: float = 1.0  # never derived from capital contribution
    reason_visible_to_collective: bool = True
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def enforce_one_member_one_voice(self, capital_contribution_amount: float = 0.0) -> None:
        """Explicit decoupling: capital amount never modifies vote weight."""
        # Weight remains fixed at 1.0 regardless of contribution.
        # This method exists to make the decoupling auditable and explicit.
        self.weight = 1.0


def compute_consensus_result(vote_records: list[GovernanceVoteRecord]) -> dict[str, Any]:
    """True consensus: no blocking objections remain after collaborative integration."""
    total = len(vote_records)
    if total == 0:
        return {"status": "no_participation", "decision": None}
    approvals = sum(1 for r in vote_records if r.vote == "approve")
    blocks = sum(1 for r in vote_records if r.vote == "block")
    # True consensus: zero blocks after objection integration phase.
    if blocks == 0:
        return {
            "status": "consensus_reached",
            "decision": "approve",
            "approval_rate": approvals / total,
            "participation_rate": total / max(total, 1),
            "blocking_objections_resolved": True,
        }
    return {
        "status": "blocked",
        "decision": None,
        "approval_rate": approvals / total,
        "blocking_objections_remaining": blocks,
        "next_step": "collaborative_objection_integration",
    }


# ------------------------------------------------------------------
# Pattern C: Consensus Process Engine (consensuscode patterns)
# ------------------------------------------------------------------

@dataclass(slots=True)
class ConsensusProposal:
    proposal_id: str
    title: str
    description: str
    affected_agent_ids: list[str]
    proposal_template_version: str = "1.0"
    submitted_by: str = ""
    status: Literal[
        "pending", "consultation_active", "objection_integration",
        "consensus_verified", "implemented", "evaluated"
    ] = "pending"
    consultation_workspace_path: str = ""

    def requires_true_consensus(self) -> bool:
        return len(self.affected_agent_ids) > 0


@dataclass(slots=True)
class ConsensusCoordinationRole:
    """Temporary, revocable coordination role (not decision authority)."""
    role_id: str
    agent_id: str
    role_type: Literal["facilitator", "documenter", "mediator"]
    revocable_by_collective_vote: bool = True
    teaching_commitment_percent: float = 50.0  # 50% teaching / 50% doing
    authority_scope: Literal["consultation_only", "documentation_only"] = "consultation_only"

    def is_temporary(self) -> bool:
        return True  # Always temporary; no permanent authority


# ------------------------------------------------------------------
# Pattern D: Cooperative Contract & Constraint Engine (coop-kernel + ICN)
# ------------------------------------------------------------------

@dataclass(slots=True)
class CooperativeCharter:
    """TOML-formatted governance constitution mapped to substrate config."""
    cooperative_id: str
    proposal_types: list[str]
    quorum_percent: float = 60.0
    approval_threshold_percent: float = 60.0
    amendment_super_majority_percent: float = 75.0
    delegation_expiry_days: int = 90
    reserve_fund_percent: float = 20.0
    complexity_multipliers: dict[str, float] = field(default_factory=dict)

    def calculate_share_from_formula(
        self, time_spent_hours: float, complexity_factor: float
    ) -> float:
        """Algorithmic fairness: Time × Complexity = Share."""
        return time_spent_hours * complexity_factor


@dataclass(slots=True)
class ConstraintSet:
    """Generic constraint returned by Policy Oracle; enforced blindly by kernel."""
    rate_limit_per_second: float | None = None
    credit_ceiling: float | None = None
    voting_weight: float | None = None
    fuel_meter_per_operation: float | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class PolicyOracle:
    """App-layer translator: domain meaning → generic ConstraintSet."""

    def __init__(self, charter: CooperativeCharter):
        self.charter = charter

    def evaluate(
        self, request: dict[str, Any]
    ) -> ConstraintSet:
        """Evaluate domain request and return generic constraints only."""
        # Meaning Firewall: no domain semantics leak through to kernel.
        # Kernel only sees rate limits, credit ceilings, voting weights.
        return ConstraintSet(
            rate_limit_per_second=request.get("requested_rate_limit"),
            credit_ceiling=self.credit_ceiling_for_request(request),
            voting_weight=self.voting_weight_for_member(
                request.get("member_id", "")
            ),
        )

    def credit_ceiling_for_request(self, request: dict[str, Any]) -> float | None:
        # Default: no artificial ceiling unless governance specifies.
        return None

    def voting_weight_for_member(self, member_id: str) -> float | None:
        # One-person-one-voice: weight always 1.0 regardless of capital.
        return 1.0


# ------------------------------------------------------------------
# Pattern E: Indigenous Data Sovereignty (CARE + Customary Pillars)
# ------------------------------------------------------------------

INDIGENOUS_PILLAR_KEYS = [
    "kamachy_self_determination",
    "ayllu_llaktapak_collective_authority",
    "tantanakuy_relational_accountability",
    "willay_panka_tantay_ancestral_memory",
    "sumak_kawsay_biocultural_ethics",
]

CARE_PRINCIPLES = {
    "C": "collective_benefit",
    "A": "authority_to_control",
    "R": "responsibility",
    "E": "ethics",
}

@dataclass(slots=True)
class IndigenousDataGovernanceRecord:
    """Record enforcing Indigenous data sovereignty over digital artifacts."""
    data_artifact_id: str
    collective_identity_link: str  # data as extension of identity/kinship/territory
    ancestral_memory_provenance: str  # Willay-panka-tantay: genealogical/relational memory
    authority_holder_community_id: str
    consent_protocol_version: str = "CARE_v1"
    relational_accountability_links: list[str] = field(default_factory=list)
    biocultural_ethics_review_complete: bool = False
    ex_situ_repository_governed_by_hybrid_agreement: bool = False

    def enforce_care_principles(self) -> dict[str, bool]:
        return {
            "collective_benefit_verified": bool(self.authority_holder_community_id),
            "authority_to_control_documented": bool(self.authority_holder_community_id),
            "relational_accountability_traced": len(self.relational_accountability_links) > 0,
            "biocultural_ethics_reviewed": self.biocultural_ethics_review_complete,
        }

    def is_data_extension_of_territory_memory(self) -> bool:
        """Data is never merely resource; it is collective identity, memory, kinship, territory."""
        return bool(
            self.collective_identity_link
            and self.ancestral_memory_provenance
        )


# ------------------------------------------------------------------
# Pattern F: Federated Diplomacy (Fediverse / Covenantal Federalism)
# ------------------------------------------------------------------

@dataclass(slots=True)
class FederationCovenant:
    """Shared values articulated in advance; federation = voluntary agreement."""
    server_instance_id: str
    covenant_version: str
    shared_norms: list[str]  # e.g., ["no_hate_speech", "no_harassment", "local_moderation"]
    federation_status: Literal[
        "federated", "limited", "suspended", "defederated"
    ] = "federated"
    defederation_reason_documented: str = ""
    local_autonomy_preserved: bool = True

    def is_covenantal(self) -> bool:
        return len(self.shared_norms) > 0

    def can_federate_with(self, other: "FederationCovenant") -> bool:
        """Federation requires overlapping shared norms (not identical, but compatible)."""
        overlap = set(self.shared_norms).intersection(set(other.shared_norms))
        return len(overlap) > 0


@dataclass(slots=True)
class FederatedDiplomacyEvent:
    """Cross-instance governance action: federation, defederation, content filtering."""
    event_id: str
    source_instance: str
    target_instance: str
    action: Literal["federate", "defederate", "limit", "filter_content"]
    justification: str
    audit_log_path: str = ""
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_governance_action(self) -> bool:
        return self.action in ("federate", "defederate", "limit")


# ------------------------------------------------------------------
# Pattern G: Liberation Stack — Layer Dependency & Gate Validation
# ------------------------------------------------------------------

LIBERATION_LAYER_SPEC = [
    {"index": 1, "function": "energy", "dependencies": [], "gate": "local_energy_fraction"},
    {"index": 2, "function": "manufacturing", "dependencies": [1], "gate": "local_manufacturing_share"},
    {"index": 3, "function": "food", "dependencies": [1, 2], "gate": "local_food_security_share"},
    {"index": 4, "function": "communication", "dependencies": [1, 2, 3], "gate": "connectivity_and_literacy"},
    {"index": 5, "function": "knowledge", "dependencies": [4], "gate": "digital_literacy_transparent_rules"},
    {"index": 6, "function": "governance", "dependencies": [3, 4, 5], "gate": "connected_informed_participants"},
]


@dataclass(slots=True)
class LiberationStackDeployment:
    active_layers: set[int]
    dependency_graph_valid: bool = field(init=False)
    gate_conditions_met: dict[int, bool] = field(default_factory=dict)
    universal_desired_resources_enabled: bool = False

    def __post_init__(self):
        self._validate_dag()

    def _validate_dag(self) -> None:
        for spec in LIBERATION_LAYER_SPEC:
            deps = set(spec["dependencies"])
            self.dependency_graph_valid = deps.issubset(self.active_layers)
            if not self.dependency_graph_valid:
                break

    def evaluate_gate_condition(self, layer_index: int, context_metrics: dict[str, float]) -> bool:
        spec = next((s for s in LIBERATION_LAYER_SPEC if s["index"] == layer_index), None)
        if spec is None:
            return False
        gate_key = spec["gate"]
        # Qualitative gates evaluated against context; numerical thresholds deferred to pilot.
        metric = context_metrics.get(gate_key, 0.0)
        # For substrate: gate is considered met when metric > 0 (operational evidence exists).
        self.gate_conditions_met[layer_index] = metric > 0.0
        return self.gate_conditions_met[layer_index]

    def check_prefigurative_consistency(self) -> bool:
        """Means must embody ends: democratic systems governed democratically."""
        return self.active_layers >= {5, 6} if 5 in self.active_layers and 6 in self.active_layers else False


# ------------------------------------------------------------------
# Pattern H: Mutual Credit Ledger (Proudhonian Mutualism + coop-kernel)
# ------------------------------------------------------------------

@dataclass(slots=True)
class MutualCreditPosition:
    cooperative_id: str
    party_id: str
    credit_amount: float  # positive = owed to party; negative = owed by party
    surplus_distribution_approved_by_democratic_vote: bool = False
    audit_trail_sha256: str = ""

    def apply_surplus_distribution(self, surplus_share: float) -> None:
        """Surplus distributed democratically; not by capital share."""
        self.surplus_distribution_approved_by_democratic_vote = True
        self.credit_amount += surplus_share
        # Re-compute audit hash
        self.audit_trail_sha256 = hashlib.sha256(
            f"{self.cooperative_id}:{self.party_id}:{self.credit_amount}:{surplus_share}".encode()
        ).hexdigest()


# ------------------------------------------------------------------
# Pattern I: Sustainable Progress — Ecological Budget Constraint
# ------------------------------------------------------------------

@dataclass(slots=True)
class EcologicalBudgetConstraint:
    """Global ecological feasibility: sum of ecological footprints <= operative budget."""
    operative_budget_E: float
    request_profiles: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_request_profile(self, agent_id: str, footprint_mapping: dict[str, float]) -> None:
        self.request_profiles[agent_id] = footprint_mapping

    def is_feasible(self, footprint_phi: callable) -> bool:
        total = sum(
            footprint_phi(profile) for profile in self.request_profiles.values()
        )
        return total <= self.operative_budget_E


# ------------------------------------------------------------------
# Module-level Registry & Verification
# ------------------------------------------------------------------

def register_decentralized_governance_standard():
    """Registers this module's patterns as substrate-standards-compliant components."""
    return {
        "module": "substrate.decentralized_governance",
        "patterns_implemented": [
            "polycentric_governance_overlay",
            "capital_governance_decoupling",
            "true_consensus_engine",
            "cooperative_contract_constraint_engine",
            "indigenous_data_sovereignty_layer",
            "federated_diplomacy",
            "liberation_stack_dependency_validation",
            "mutual_credit_ledger",
            "ecological_budget_constraint",
        ],
        "non_westernized_perspectives_included": True,
        "transparent_value_systems": True,
        "audit_artifacts_available": True,
    }
