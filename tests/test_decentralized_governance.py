"""Verification tests for decentralized governance substrate components."""

from substrate.decentralized_governance import (
    DIGNITY_STACK_LAYERS,
    ConstraintSet,
    CooperativeCharter,
    EcologicalBudgetConstraint,
    FederationCovenant,
    GovernanceVoteRecord,
    IndigenousDataGovernanceRecord,
    LiberationStackDeployment,
    MutualCreditPosition,
    PolicyOracle,
    compute_consensus_result,
    register_decentralized_governance_standard,
)


def test_dignity_stack_layers_defined():
    assert len(DIGNITY_STACK_LAYERS) == 6
    dimensions = [layer.dimension for layer in DIGNITY_STACK_LAYERS]
    assert "technological_oversight" in dimensions
    assert "economic_justice" in dimensions


def test_dignity_dependencies_valid():
    active = {1, 2, 3, 4, 5, 6}
    for layer in DIGNITY_STACK_LAYERS:
        assert layer.verify_dependencies(active)


def test_capital_governance_decoupling():
    """Vote weight never modified by capital contribution."""
    record = GovernanceVoteRecord(
        member_id="m-01",
        proposal_id="prop-01",
        vote="approve",
    )
    # Even with large capital contribution, weight remains 1.0
    record.enforce_one_member_one_voice(capital_contribution_amount=100000.0)
    assert record.weight == 1.0


def test_true_consensus_result():
    records = [
        GovernanceVoteRecord("a", "p1", "approve"),
        GovernanceVoteRecord("b", "p1", "approve"),
    ]
    result = compute_consensus_result(records)
    assert result["status"] == "consensus_reached"
    assert result["blocking_objections_resolved"] is True


def test_true_consensus_blocked():
    records = [
        GovernanceVoteRecord("a", "p1", "approve"),
        GovernanceVoteRecord("b", "p1", "block"),
    ]
    result = compute_consensus_result(records)
    assert result["status"] == "blocked"
    assert result["blocking_objections_remaining"] == 1


def test_cooperative_formula_fairness():
    charter = CooperativeCharter(
        cooperative_id="coop-test",
        proposal_types=["budget"],
        complexity_multipliers={"backend": 1.5, "docs": 1.0},
    )
    share = charter.calculate_share_from_formula(10.0, 1.5)
    assert share == 15.0


def test_indigenous_care_principles():
    record = IndigenousDataGovernanceRecord(
        data_artifact_id="art-01",
        collective_identity_link="link-01",
        ancestral_memory_provenance="prov-01",
        authority_holder_community_id="community-01",
        relational_accountability_links=["r-01"],
        biocultural_ethics_review_complete=True,
    )
    care = record.enforce_care_principles()
    assert all(care.values())
    assert record.is_data_extension_of_territory_memory()


def test_federation_covenant():
    covenant = FederationCovenant(
        server_instance_id="instance-01",
        covenant_version="1.0",
        shared_norms=["commons_governance", "universal_care"],
    )
    assert covenant.is_covenantal()
    other = FederationCovenant(
        server_instance_id="instance-02",
        covenant_version="1.0",
        shared_norms=["commons_governance"],
    )
    assert covenant.can_federate_with(other)


def test_liberation_stack_dag_valid():
    lib = LiberationStackDeployment(active_layers={1, 2, 3, 4, 5, 6})
    assert lib.dependency_graph_valid
    assert lib.check_prefigurative_consistency()


def test_policy_oracle_constraint_firewall():
    charter = CooperativeCharter(cooperative_id="coop-oracle-test", proposal_types=["budget"])
    oracle = PolicyOracle(charter)
    result = oracle.evaluate({"member_id": "m-01", "requested_rate_limit": 10})
    assert isinstance(result, ConstraintSet)
    assert result.voting_weight == 1.0  # Always 1.0 regardless of capital


def test_mutual_credit_audit():
    position = MutualCreditPosition(
        cooperative_id="coop-01",
        party_id="party-01",
        credit_amount=100.0,
    )
    original_hash = position.audit_trail_sha256
    position.apply_surplus_distribution(25.0)
    assert position.surplus_distribution_approved_by_democratic_vote
    assert position.audit_trail_sha256 != original_hash


def test_ecological_budget():
    budget = EcologicalBudgetConstraint(operative_budget_E=100.0)
    budget.add_request_profile("agent-01", {"resource_use": 30.0})
    # Simple footprint function
    def phi(profile):
        return profile.get("resource_use", 0.0)
    assert budget.is_feasible(phi)
    budget.add_request_profile("agent-02", {"resource_use": 85.0})
    assert not budget.is_feasible(phi)


def test_standard_registration():
    std = register_decentralized_governance_standard()
    assert std["module"] == "substrate.decentralized_governance"
    assert len(std["patterns_implemented"]) == 9
    assert std["non_westernized_perspectives_included"] is True
