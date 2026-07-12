"""Auto-remediation: Playbook config, Safety Limits, and the decision engine.

See ``docs/adr/007-remediation-safety.md``. A Playbook maps a ``rule_key``
(the same ``"{kind}:{metric_type}"`` string an ``Alert`` carries) to a
named, parameterized action. Remediation is only ever *considered* at the
same point an alert escalates (``AlertEvaluationService``) — never on open
or on a plain still-firing advance — so a human always has a chance to act
first.
"""
