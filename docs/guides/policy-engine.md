---
title: "Policy Engine"
description: "Define, version, and enforce governance policies over knowledge graph decisions — with compliance checking, violation tracking, impact analysis, and multi-level approval workflows."
icon: "scale-balanced"
---

## What Is Policy Engine?

Policy evaluation is the systematic checking of decisions against predefined governance rules and constraints. Unlike application enforcement that automatically blocks non-compliant actions, policy evaluation provides compliance status that can trigger different workflows—approval processes, exception handling, or audit requirements.

**Key policy concepts:**

**Policy evaluation** checks whether decisions meet defined criteria without automatically preventing actions, enabling flexible governance workflows.

**Governance and compliance workflows** use policy evaluation results to route decisions through appropriate approval chains, exception processes, or audit trails.

**Approval processes** can be triggered by policy violations, creating documented exception paths with justification and approver accountability.

**Difference from enforcement:** Policy evaluation returns compliance status (`True`/`False`) but does not automatically block actions. Your workflow determines what happens next—immediate approval, escalation, exception handling, or rejection.

## Why Use Policy Engine?

**Governance and accountability.** Create auditable decision workflows where every policy evaluation, exception, and approval is permanently recorded in the knowledge graph with full provenance tracking.

**Compliance verification.** Systematically check decisions against regulatory requirements, internal policies, and risk management rules before they are finalized or acted upon.

**Approval workflow orchestration.** Route non-compliant decisions through structured approval processes with documented justifications and multi-level sign-offs.

**Regulatory compliance.** Meet audit requirements by maintaining complete policy version histories, exception records, and compliance checking trails that regulators can inspect.

**Risk management.** Flag high-risk decisions for additional review while allowing routine compliant decisions to proceed with minimal friction.

**Policy evolution tracking.** Maintain version histories of policy changes with impact analysis, enabling evidence-based policy refinement and regulatory reporting.

## When To Use / When Not To Use

**Use Policy Engine for:**
- Governance workflows requiring structured approval processes and audit trails
- Regulatory compliance where policy adherence must be documented and verifiable
- Multi-level approval workflows for high-stakes decisions (financial approvals, security exceptions, clinical treatments)
- Regulated environments where policy violations trigger specific escalation procedures
- Risk management workflows where non-compliant decisions require additional oversight
- Audit requirements demanding complete policy application and exception tracking

**Do NOT use Policy Engine for:**
- Simple form validation or basic input checking—use standard validation libraries instead
- Basic business rules that don't require audit trails or governance workflows  
- Low-stakes, high-throughput checks where policy evaluation overhead would impact performance
- Deterministic rule checking that doesn't benefit from version tracking and approval processes
- Real-time operational decisions where policy evaluation latency is unacceptable

**Warning:** Policy Engine adds governance overhead and requires careful workflow design. Only use when the benefits of structured policy management outweigh the additional complexity.

`PolicyEngine` enforces named policies against recorded decisions, returning `True` if the decision satisfies all policy rules. Use it to gate AI decisions at runtime — attributions requiring dual-source confirmation, escalations requiring senior approval, or any decision category where compliance must be verified before the outcome is recorded. Policies are versioned graph nodes, so every check, exception, and approval chain is part of the permanent audit trail.

<Info>
The Policy Engine sits above `AgentContext` and `ContextGraph`. Policies are stored as nodes in the same graph as decisions, giving them the same causal tracing, provenance, and temporal validity as any other knowledge graph entity. 

**Key objects:** `PolicyEngine` and `Policy` import from `semantica.context`. `Decision` is a dataclass with fields like `decision_id`, `category`, `scenario`, `reasoning`, `outcome`, `confidence`, `timestamp`, `decision_maker`, and `metadata`. `DecisionRecorder` imports from `semantica.context.decision_recorder` for approval workflow tracking.
</Info>

## Supported Rule Types

The PolicyEngine implementation supports specific rule patterns that evaluate decision attributes and metadata:

**Confidence rules:**
- `min_confidence: 0.85` — `decision.confidence >= 0.85`

**Outcome validation:**
- `allowed_outcomes: ["approved", "approved_with_conditions"]` — `decision.outcome` must be in the list

**Category validation:**
- `required_categories: ["credit_risk", "operational_risk"]` — `decision.category` must be in the list

**Metadata field rules:**
- `min_*: value` — metadata field must be `>= value` (e.g., `min_credit_score: 680`)
- `max_*: value` — metadata field must be `<= value` (e.g., `max_ltv: 0.85`)
- `required_*: value` — metadata field must equal `value` (string) or contain all items (list)

**Field lookup behavior:** For rule `min_credit_score`, the engine checks `metadata["credit_score"]`, then `metadata["*_credit_score"]` (suffix match), then `decision.credit_score` attribute.

**Important:** The following rule types are NOT supported and will cause unexpected behavior:
- `disallowed_outcomes` (use `allowed_outcomes` instead)
- `mandatory_fields` (use `required_*` for specific fields)
- `requires_mfa` (use metadata field checks like `required_mfa_verified`)
- Complex nested conditions or operators

---

## Defining the policy

A `Policy` is a dataclass with a free-form `rules` dict — encode whatever your domain requires using supported rule patterns.

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
        "allowed_outcomes":         ["nation_state_attributed_dual_source"],
        "min_confidence":           0.85,
        "required_source_a":        True,
        "required_source_b":        True,
        "required_approver":        True,
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
    metadata      = {
        "independent_sources": 1,  # Below min_independent_sources requirement
        "approver_role": "analyst",  # Below required_approver_role
        "source_a": True,  # Has first source
        # Missing source_b and approver fields
    }
)

is_compliant = engine.check_compliance(decision, policy_id)
print(f"Compliant: {is_compliant}")
# Compliant: False
#
# Multiple rule violations:
# - outcome "nation_state_attributed_single_source" not in allowed_outcomes
# - independent_sources (1) < min_independent_sources (2)
# - approver_role "analyst" != required_approver_role "senior_analyst"
# - missing required_source_b and required_approver fields
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
engine.update_policy(
    policy_id     = policy_id,
    rules         = {**current_policy.rules, "min_confidence": 0.92},
    change_reason = "Q3 attribution quality review — raise confidence floor from 0.85 to 0.92 "
                    "to reduce false-positive nation-state attributions",
    new_version   = "1.1.0",
)

print(f"Policy updated: {policy_id} to version 1.1.0")
# Policy updated: pol-attr-001 to version 1.1.0

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

## Common Pitfalls

**Assuming failed compliance automatically blocks actions.** PolicyEngine returns compliance status but does NOT automatically prevent actions. Your workflow must check the returned boolean and decide what happens next—approval, rejection, exception handling, or escalation.

**Using unsupported rule keys.** The implementation only supports specific patterns: `min_*`, `max_*`, `required_*`, `min_confidence`, `allowed_outcomes`, and `required_categories`. Any other rule key falls back to a key-presence check: it passes only if that exact key exists in `decision.metadata`, regardless of its value. This means keys like `disallowed_outcomes` will silently **fail** compliance whenever that literal key is absent from metadata (the common case), and will silently **pass** — regardless of the actual outcome — if a `disallowed_outcomes` key happens to exist in metadata with any value. Neither behavior matches the intended "outcome must not be in this list" semantics — use `allowed_outcomes` instead.

**Treating exceptions as approvals.** Recording a policy exception with `record_exception()` does NOT automatically make a non-compliant decision compliant. Exceptions are audit trail entries—your workflow must still decide whether to proceed with the non-compliant decision.

**Assuming PolicyEngine modifies graph state automatically.** PolicyEngine only evaluates compliance and records policy applications, exceptions, and approval chains. It does not modify decision outcomes, metadata, or prevent actions—that is your workflow's responsibility.

**Using complex nested rule structures.** The implementation does not support complex conditional logic, nested operators, or arbitrary expressions. Keep rules simple: single field comparisons, list membership checks, and threshold validations only.

**Missing metadata for rule evaluation.** Rules like `min_credit_score` require the corresponding metadata field (`credit_score`) to be present in `decision.metadata`. Missing metadata fields cause rule evaluation to fail, making the decision non-compliant.

**Forgetting to check rule evaluation results.** Always handle both compliant and non-compliant cases explicitly. Non-compliant decisions that proceed without proper exception handling create audit gaps and governance risks.

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
        "required_classification":      "TLP:RED",
        "allowed_outcomes":             ["retained_internal", "escalated_internal"],
        "min_confidence":               0.95,
        "required_tlp":                 True,
        "required_authorised_recipients": True,
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
    outcome       = "shared_with_partner",   # violates allowed_outcomes policy
    confidence    = 0.88,                    # below min_confidence threshold
    timestamp     = datetime.utcnow(),
    decision_maker= "analyst_rodriguez",
    metadata      = {
        "classification": "TLP:RED",
        "tlp": True,
        "authorised_recipients": True,
    }
)

is_compliant = engine.check_compliance(decision, "pol-opsec-001")
print(f"Compliant: {is_compliant}")
# Compliant: False — outcome 'shared_with_partner' not in allowed_outcomes; confidence below 0.95

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
        methods     = ["email",             "zoom_call"],
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
            "required_mfa_verified":       True,
            "allowed_outcomes":            ["access_granted_with_mfa"],
            "min_confidence":              0.90,
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
            "required_pam_session":        True,
            "required_session_recording":  True,
            "max_session_hours":           4,
            "allowed_outcomes":            ["privileged_access_granted_with_pam"],
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
    metadata      = {
        "pam_session": False,      # PAM checkout failed
        "session_recording": True, # Manual recording in place
        "session_hours": 3,        # Planned session duration
    }
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
        "min_egfr":                    30,      # eGFR must be >= 30
        "allowed_outcomes":            ["metformin_discontinued", "metformin_contraindicated", "alternative_prescribed"],
        "required_clinician_sign_off": True,
        "required_egfr_check":         True,
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
    metadata      = {
        "egfr": 28,                    # Below minimum threshold
        "clinician_sign_off": True,
        "egfr_check": True,
        "drug": "metformin",
    }
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
        "min_stress_test_bps":             300,
        "allowed_outcomes":                ["approved", "approved_with_conditions"],
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
    outcome       = "approved_ltv_exception",   # not in allowed_outcomes — flags non-compliance
    confidence    = 0.72,
    timestamp     = datetime.utcnow(),
    decision_maker= "underwriting_model_v4",
    metadata      = {
        "ltv": 0.86,           # Exceeds max_ltv of 0.85
        "dsti": 0.38,          # Within max_dsti of 0.40
        "credit_score": 710,   # Above min_credit_score of 680
        "pd": 0.023,           # Recorded for audit — no threshold rule in this policy
        "lgd": 0.45,           # Recorded for audit — no threshold rule in this policy
        "stress_test_bps": 300,
    }
)

is_compliant = engine.check_compliance(decision, "pol-credit-001")
print(f"Compliant: {is_compliant}")
# Compliant: False — ltv (0.86) > max_ltv (0.85) and outcome not in allowed_outcomes

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

- [Decision Intelligence](/guides/decision-intelligence) — `record_decision()`, causal chains, and precedent search — the decisions that `check_compliance()` evaluates
- [Reasoning & Rules](reasoning) — complement policy rules with formal inference for logical conflict detection
- [SHACL Validation](/guides/shacl-validation) — enforce structural constraints on policy nodes themselves
- [Change Management](/guides/change-management) — version-snapshot the policy graph alongside the knowledge graph
- [Provenance](provenance) — W3C PROV-O lineage for every policy decision and exception
- [MCP Server](/guides/mcp-server) — expose `record_decision` and `find_precedents` as MCP tools for AI agents
