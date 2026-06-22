---
title: "Policy Engine"
description: "Define, version, and enforce governance policies over knowledge graph decisions — with compliance checking, violation tracking, impact analysis, and multi-level approval workflows."
icon: "scale-balanced"
---

`PolicyEngine` enforces named policies against recorded decisions, returning `True` if the decision satisfies all policy rules. Use it to gate AI decisions at runtime — attributions requiring dual-source confirmation, escalations requiring senior approval, or any decision category where compliance must be verified before the outcome is recorded. Policies are versioned graph nodes, so every check, exception, and approval chain is part of the permanent audit trail.

<Info>
The Policy Engine sits above `AgentContext` and `ContextGraph`. Policies are stored as nodes in the same graph as decisions, giving them the same causal tracing, provenance, and temporal validity as any other knowledge graph entity. `PolicyEngine` and `Policy` import from `semantica.context`. `Decision` imports from `semantica.context` (it is a dataclass defined in `semantica.context.decision_models`). `DecisionRecorder` imports from `semantica.context.decision_recorder`.
</Info>

---

## Defining the policy

A `Policy` is a dataclass with a free-form `rules` dict — encode whatever your domain requires.

```python
from semantica.context import ContextGraph, PolicyEngine, Policy
from datetime import datetime

graph  = ContextGraph()
engine = PolicyEngine(graph_store=graph)

attribution_policy = Policy(
    policy_id   = "pol-attr-001",
    name        = "Nation-State Attribution — Dual Source + Senior Approval",
    description = (
        "Attributions to nation-state actors require corroboration from two independent "
        "intelligence sources and explicit senior analyst approval before being recorded "
        "in the authoritative graph."
    ),
    rules = {
        "min_independent_sources":  2,
        "required_approver_role":   "senior_analyst",
        "disallowed_outcomes":      ["nation_state_attributed_single_source"],
        "min_confidence":           0.85,
        "mandatory_fields":         ["source_a", "source_b", "approver"],
    },
    category   = "threat_attribution",
    version    = "1.0.0",
    created_at = datetime.utcnow(),
    updated_at = datetime.utcnow(),
)

policy_id = engine.add_policy(attribution_policy)
print(f"Policy registered: {policy_id}")
# Policy registered: pol-attr-001
```

The policy is now a node in the graph. It has a version string, a creation timestamp, and a `rules` dict that the compliance checker will read when evaluating decisions against it.

---

## Checking a decision for compliance

`check_compliance` takes a `Decision` object and the policy ID and returns a boolean.

```python
from semantica.context import Decision

# The AI analyst's APT29 attribution — only one source cited, no senior approval yet
decision = Decision(
    decision_id   = "",                        # auto-generated if left empty
    category      = "threat_attribution",
    scenario      = "APT29 activity cluster in NATO network telemetry Q2 2025",
    reasoning     = (
        "Observed TTPs match APT29 historical patterns: HAMMERTOSS C2, "
        "spear-phishing via OneDrive lure, targeting foreign ministry staff. "
        "Single source: internal SIEM telemetry."
    ),
    outcome       = "nation_state_attributed_single_source",
    confidence    = 0.91,
    timestamp     = datetime.utcnow(),
    decision_maker= "ai_threat_analyst_v3",
)

is_compliant = engine.check_compliance(decision, policy_id)
print(f"Compliant: {is_compliant}")
# Compliant: False
#
# The outcome "nation_state_attributed_single_source" is in disallowed_outcomes.
# The policy requires min_independent_sources=2 — the decision only cited one.
```

The engine returns `False`. The decision has not been rejected — it has been flagged. What happens next depends on your workflow. In some organisations, a non-compliant result simply blocks the write to the authoritative graph. In others, it triggers an exception process where a human approver reviews the evidence and signs off.

---

## Recording a policy exception

`record_exception` permanently links a decision, the policy it violated, the approver identity, and the justification.

```python
exception_id = engine.record_exception(
    decision_id  = decision.decision_id,
    policy_id    = policy_id,
    reason       = "Time-sensitive attribution — protective action required before second source available",
    approver     = "sr_analyst_chen",
    justification= (
        "Senior analyst reviewed SIEM telemetry and concurs with TTP matching. "
        "Exception approved under Emergency Attribution Procedure §3.2. "
        "Second source corroboration to be completed within 72 hours."
    ),
)

print(f"Exception recorded: {exception_id}")
# Exception recorded: exc-pol-attr-001-20250621-001
#
# The exception node is linked to both the decision and the policy in the graph,
# creating a permanent three-way provenance link: decision → exception → policy.
```

---

## Building a multi-level approval chain

For the highest-stakes decisions — formal attribution reports that will be shared with government partners — a single approver is not enough. Three people need to sign off: the team lead, the department head, and the CISO. `DecisionRecorder.record_approval_chain` captures all three in a single call, linking each approver to the communication method and context of their sign-off.

```python
from semantica.context.decision_recorder import DecisionRecorder

recorder = DecisionRecorder(graph_store=graph)

# approvers, methods, and contexts must be equal-length parallel lists
recorder.record_approval_chain(
    decision_id = decision.decision_id,
    approvers   = ["team_lead_okonkwo",  "dept_head_zhang",    "ciso_miller"],
    methods     = ["slack_dm",            "zoom_call",           "email"],
    contexts    = [
        "Team lead reviewed TTPs and SIEM evidence",
        "Dept head approved sharing with Five Eyes partners",
        "CISO authorised formal nation-state attribution report",
    ],
)

print("Three-level approval chain recorded")
# The graph now carries a directed approval chain:
#   decision → team_lead_okonkwo → dept_head_zhang → ciso_miller
# Each link is stamped with method and context for Inspector General review.
```

---

## What-if impact analysis before changing a policy

Six months on, your threat intelligence lead wants to tighten the policy: raise the minimum confidence threshold from 0.85 to 0.92 to reduce false-positive attributions. Before she updates the policy, she wants to know how many past decisions would have been blocked under the stricter rule.

`analyze_policy_impact` runs a what-if simulation over the historical decision record — no permanent changes are made.

```python
current_policy = engine.get_policy(policy_id)

impact = engine.analyze_policy_impact(
    policy_id      = policy_id,
    proposed_rules = {**current_policy.rules, "min_confidence": 0.92},
)

print(f"Decisions affected by raising confidence floor to 0.92: {impact.get('affected_decisions', 0)}")
# Decisions affected by raising confidence floor to 0.92: 4
#
# Four past attributions had confidence between 0.85 and 0.92.
# Under the new rule, all four would have required exceptions.
# The lead can now make an evidence-based choice: is that trade-off acceptable?
```

The impact dict contains per-decision detail, not just the count. You can inspect which specific attribution decisions would have been affected, review their reasoning, and decide whether tightening the threshold is worth it.

---

## Updating the policy and finding affected decisions

The lead decides to proceed with the threshold increase. She updates the policy to version 1.1.0, recording her reason. The old version is preserved in the history.

```python
updated_policy_id = engine.update_policy(
    policy_id     = policy_id,
    rules         = {**current_policy.rules, "min_confidence": 0.92},
    change_reason = "Q3 attribution quality review — raise confidence floor from 0.85 to 0.92 "
                    "to reduce false-positive nation-state attributions",
    new_version   = "1.1.0",
)

print(f"Policy updated: {updated_policy_id} -> version 1.1.0")
# Policy updated: pol-attr-001 -> version 1.1.0

# Find all decisions that were evaluated under v1.0.0 —
# these need to be re-reviewed to confirm they still meet the new standard.
affected = engine.get_affected_decisions(
    policy_id    = policy_id,
    from_version = "1.0.0",
    to_version   = "1.1.0",
)

print(f"Decisions to re-audit: {len(affected)}")
for dec in affected:
    print(f"  {dec.get('decision_id')}  confidence={dec.get('confidence')}  outcome={dec.get('outcome')}")
# decision-a3f1  confidence=0.87  outcome=nation_state_attributed
# decision-b22c  confidence=0.89  outcome=nation_state_attributed
# ...
```

This is the re-audit workflow: every decision made under the old policy is surfaced, reviewed against the new standard, and either re-confirmed or flagged for correction. The graph preserves the full history of which policy version governed each decision.

---

## Reviewing the full audit trail

At any point — for an Inspector General review, a board report, or an incident investigation — you can retrieve the complete version history of a policy.

```python
history = engine.get_policy_history(policy_id)

print(f"Policy versions on record: {len(history)}")
for version in history:
    print(f"  v{version.version}  updated={version.updated_at.date()}  rules_keys={list(version.rules.keys())}")
# v1.0.0  updated=2025-06-21  rules_keys=[min_independent_sources, required_approver_role, ...]
# v1.1.0  updated=2025-09-14  rules_keys=[min_independent_sources, required_approver_role, ...]
#
# The full rules dict for each version is preserved — you can replay exactly
# what the compliance check would have returned for any past decision against
# any past version of the policy.
```

---

## Domain Examples

<Tabs>

<Tab title="Defense — CTI/Threat">

TLP:RED intelligence must never be shared outside the originating organisation without commander-level approval. The policy is enforced on every information-sharing decision that touches classified threat reporting. Violations are routed to the J2 officer for exception review rather than silently logged.

```python
from semantica.context import ContextGraph, PolicyEngine, Policy, Decision
from semantica.context.decision_recorder import DecisionRecorder
from datetime import datetime

graph    = ContextGraph()
engine   = PolicyEngine(graph_store=graph)
recorder = DecisionRecorder(graph_store=graph)

opsec_policy = Policy(
    policy_id   = "pol-opsec-001",
    name        = "TLP:RED — Restricted Dissemination",
    description = "TLP:RED intelligence must not be shared outside the originating organisation",
    rules = {
        "classification":      "TLP:RED",
        "disallowed_outcomes": ["shared_with_partner", "published"],
        "min_confidence":      0.95,
        "mandatory_fields":    ["tlp", "classification", "authorised_recipients"],
    },
    category   = "information_sharing",
    version    = "2.1.0",
    created_at = datetime.utcnow(),
    updated_at = datetime.utcnow(),
)
engine.add_policy(opsec_policy)

decision = Decision(
    decision_id   = "",
    category      = "information_sharing",
    scenario      = "APT29 SIGINT report TLP:RED — share with Five Eyes partners?",
    reasoning     = "Tactical intelligence — partner request via UKIC liaison",
    outcome       = "shared_with_partner",   # violates TLP:RED policy
    confidence    = 0.88,
    timestamp     = datetime.utcnow(),
    decision_maker= "analyst_rodriguez",
)

is_compliant = engine.check_compliance(decision, "pol-opsec-001")
print(f"Compliant: {is_compliant}")
# Compliant: False — outcome 'shared_with_partner' is disallowed; confidence below 0.95

if not is_compliant:
    # Route to J2 for exception review — dual commander approval required
    exception_id = engine.record_exception(
        decision_id  = decision.decision_id,
        policy_id    = "pol-opsec-001",
        reason       = "Five Eyes partner urgent request — time-critical tactical intelligence",
        approver     = "j2_officer_hayes",
        justification= "Commander approved limited dissemination under UKUSA Article 4 emergency clause",
    )
    recorder.record_approval_chain(
        decision_id = decision.decision_id,
        approvers   = ["j2_officer_hayes", "unit_commander_brooks"],
        methods     = ["secure_phone",      "in_person"],
        contexts    = ["J2 tactical review", "Commander emergency approval"],
    )
    print(f"Exception recorded with dual-commander approval: {exception_id}")

# Version history for Inspector General review
history = engine.get_policy_history("pol-opsec-001")
print(f"Policy versions on record: {len(history)}")
```

</Tab>

<Tab title="Security — SOC/Incident">

Zero-trust access policies enforce MFA for Tier-1 systems and PAM session checkout for privileged accounts. Every automated access decision is checked against both policies. When the PAM portal is unavailable during an emergency patch window, the SOC lead records a time-bounded exception with her sign-off before the work begins — not after.

```python
from semantica.context import ContextGraph, PolicyEngine, Policy, Decision
from datetime import datetime

graph  = ContextGraph()
engine = PolicyEngine(graph_store=graph)

for pol in [
    Policy(
        policy_id   = "pol-zt-mfa",
        name        = "MFA Required — All Tier-1",
        description = "Every Tier-1 access decision must verify MFA",
        rules       = {
            "requires_mfa":        True,
            "disallowed_outcomes": ["access_granted_without_mfa"],
            "min_confidence":      0.90,
        },
        category   = "access_control",
        version    = "1.0.0",
        created_at = datetime.utcnow(),
        updated_at = datetime.utcnow(),
    ),
    Policy(
        policy_id   = "pol-zt-pam",
        name        = "PAM Checkout — Privileged Accounts",
        description = "Privileged account use requires PAM session checkout",
        rules       = {
            "requires_pam":        True,
            "session_recording":   True,
            "max_session_hours":   4,
            "disallowed_outcomes": ["privileged_access_granted_no_pam"],
        },
        category   = "privileged_access",
        version    = "1.0.0",
        created_at = datetime.utcnow(),
        updated_at = datetime.utcnow(),
    ),
]:
    engine.add_policy(pol)

# Emergency patch window — PAM portal down
decision = Decision(
    decision_id   = "",
    category      = "privileged_access",
    scenario      = "sysadmin_kim patching DC-04 — PAM portal unreachable",
    reasoning     = "Critical patch CVE-2025-1234 — 4-hour RTO — PAM portal offline",
    outcome       = "privileged_access_granted_no_pam",
    confidence    = 0.78,
    timestamp     = datetime.utcnow(),
    decision_maker= "soc_automation",
)

pam_compliant = engine.check_compliance(decision, "pol-zt-pam")
print(f"PAM policy compliant: {pam_compliant}")
# PAM policy compliant: False

# SOC lead records the exception before work begins
exception_id = engine.record_exception(
    decision_id  = decision.decision_id,
    policy_id    = "pol-zt-pam",
    reason       = "PAM portal offline during critical patch window",
    approver     = "soc_lead_okafor",
    justification= "Emergency patch approved under BCP §7.3 — manual session logging in place",
)

# What-if: impact of cutting max session hours from 4 to 2 for board risk review
pam_policy = engine.get_policy("pol-zt-pam")
impact = engine.analyze_policy_impact(
    policy_id      = "pol-zt-pam",
    proposed_rules = {**pam_policy.rules, "max_session_hours": 2},
)
print(f"Decisions affected by tighter session cap: {impact.get('affected_decisions', 0)}")
```

</Tab>

<Tab title="Life Science — Clinical/Pharma">

An absolute drug contraindication policy prevents metformin from being prescribed when eGFR is below 30. The AI clinical decision-support system checks every prescribing decision against this policy before it reaches the EHR. When a borderline case requires a clinical exception, a three-person MDT approval chain is recorded — consultant, renal specialist, and pharmacist — before the prescription is issued.

```python
from semantica.context import ContextGraph, PolicyEngine, Policy, Decision
from semantica.context.decision_recorder import DecisionRecorder
from datetime import datetime

graph    = ContextGraph()
engine   = PolicyEngine(graph_store=graph)
recorder = DecisionRecorder(graph_store=graph)

safety_policy = Policy(
    policy_id   = "pol-clin-001",
    name        = "Metformin Absolute Contraindication — eGFR < 30",
    description = "Metformin must not be prescribed when eGFR is below 30 ml/min/1.73m²",
    rules = {
        "contraindicated_drug":        "metformin",
        "contraindication_condition":  {"egfr": {"operator": "<", "threshold": 30}},
        "disallowed_outcomes":         ["metformin_prescribed", "metformin_continued"],
        "requires_clinician_sign_off": True,
        "mandatory_checks":            ["egfr_measured_within_90_days"],
    },
    category   = "clinical_safety",
    version    = "3.0.0",   # aligned to BNF 2024
    created_at = datetime.utcnow(),
    updated_at = datetime.utcnow(),
    metadata   = {"source": "BNF_2024", "strength": "absolute"},
)
engine.add_policy(safety_policy)

# AI decision-support recommendation
decision = Decision(
    decision_id   = "",
    category      = "treatment_modification",
    scenario      = "PT-00841: T2DM, eGFR 28 — metformin review",
    reasoning     = "eGFR 28 is below the 30 threshold; discontinue metformin and initiate SGLT2i",
    outcome       = "metformin_discontinued_dapagliflozin_initiated",
    confidence    = 0.97,
    timestamp     = datetime.utcnow(),
    decision_maker= "cdss_v4",
)

is_compliant = engine.check_compliance(decision, "pol-clin-001")
print(f"Compliant: {is_compliant}")
# Compliant: True — outcome is metformin_discontinued, which is allowed

# MDT approval chain for the prescribing record
recorder.record_approval_chain(
    decision_id = decision.decision_id,
    approvers   = ["dr_okonkwo",  "consultant_renal_patel", "pharmacist_kwon"],
    methods     = ["zoom_call",    "zoom_call",               "email"],
    contexts    = [
        "Prescribing physician MDT review",
        "Renal consultant confirmed eGFR 28 — supports discontinuation",
        "Clinical pharmacist approved SGLT2i initiation protocol",
    ],
)
print("MDT approval chain recorded — prescription safe to issue")

# Policy version history for CQC inspection
history = engine.get_policy_history("pol-clin-001")
print(f"Policy versions on record: {len(history)}")
```

</Tab>

<Tab title="Banking — Risk/Compliance">

A Basel III mortgage underwriting policy caps LTV at 85% and DSTI at 40%. The credit model checks every origination decision against this policy before booking. When the credit committee wants to raise the minimum credit score floor before the next quarter, the impact analysis shows how many approved loans in the current book would not have passed the new rule — and the audit trail for the policy change goes to the board risk committee.

```python
from semantica.context import ContextGraph, PolicyEngine, Policy, Decision
from datetime import datetime

graph  = ContextGraph()
engine = PolicyEngine(graph_store=graph)

mortgage_policy = Policy(
    policy_id   = "pol-credit-001",
    name        = "Retail Mortgage Underwriting — Basel III CRE20",
    description = "Standard residential mortgage policy aligned to Basel III CRE20",
    rules = {
        "max_ltv":                         0.85,
        "max_dsti":                        0.40,
        "min_credit_score":                680,
        "required_stress_test_bps":        300,
        "required_fields":                 ["ltv", "pd", "lgd", "dsti", "credit_score"],
        "disallowed_outcomes":             ["approved_ltv_over_85", "approved_dsti_over_40"],
        "required_approvers_if_exception": ["senior_underwriter", "credit_committee"],
    },
    category   = "credit_risk",
    version    = "2.3.0",
    created_at = datetime.utcnow(),
    updated_at = datetime.utcnow(),
    metadata   = {"regulatory_basis": "Basel_III_CRE20", "effective_date": "2025-01-01"},
)
engine.add_policy(mortgage_policy)

# Borderline decision — LTV 86%, one point over the cap
decision = Decision(
    decision_id   = "",
    category      = "mortgage_origination",
    scenario      = "APP-2025-9921: £320k mortgage, LTV 86%, DSTI 38%, credit score 710",
    reasoning     = (
        "LTV 86% exceeds 85% cap. Stress test at +300bps passes. "
        "Credit score 710 above 680 floor. DSTI 38% within 40% limit."
    ),
    outcome       = "approved_ltv_over_85",   # disallowed outcome — flags non-compliance
    confidence    = 0.72,
    timestamp     = datetime.utcnow(),
    decision_maker= "underwriting_model_v4",
)

is_compliant = engine.check_compliance(decision, "pol-credit-001")
print(f"Compliant: {is_compliant}")
# Compliant: False — 'approved_ltv_over_85' is in disallowed_outcomes

if not is_compliant:
    exception_id = engine.record_exception(
        decision_id  = decision.decision_id,
        policy_id    = "pol-credit-001",
        reason       = "LTV 86% — one point over cap; stress test and all other metrics pass",
        approver     = "sr_underwriter_walsh",
        justification= "Credit committee approved exception under high-quality borrower criteria §4.1",
    )
    print(f"Exception recorded: {exception_id}")

# What-if before raising the credit score floor — present to board risk committee
impact = engine.analyze_policy_impact(
    policy_id      = "pol-credit-001",
    proposed_rules = {**mortgage_policy.rules, "min_credit_score": 700},
)
print(f"Decisions affected by raising credit score floor to 700: {impact.get('affected_decisions', 0)}")

# Find all decisions made under v2.3.0 — re-audit after policy update
affected = engine.get_affected_decisions("pol-credit-001", "2.3.0", "2.4.0")
print(f"Decisions to re-audit: {len(affected)}")

# Commit the update — version bump with full change attribution
engine.update_policy(
    policy_id     = "pol-credit-001",
    rules         = {**mortgage_policy.rules, "min_credit_score": 700},
    change_reason = "Credit committee Q3 review — raise score floor from 680 to 700",
    new_version   = "2.4.0",
)
print("Policy updated to v2.4.0")
```

</Tab>

</Tabs>

---

## Related Guides

- [Decision Intelligence](decision-intelligence) — `record_decision()`, causal chains, and precedent search — the decisions that `check_compliance()` evaluates
- [Reasoning & Rules](reasoning) — complement policy rules with formal inference for logical conflict detection
- [SHACL Validation](shacl-validation) — enforce structural constraints on policy nodes themselves
- [Change Management](change-management) — version-snapshot the policy graph alongside the knowledge graph
- [Provenance](provenance) — W3C PROV-O lineage for every policy decision and exception
- [MCP Server](mcp-server) — expose `record_decision` and `find_precedents` as MCP tools for AI agents
