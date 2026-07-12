"""Remediation-safety exceptions.

Reserved since Phase 0 (``docs/adr/007-remediation-safety.md``) for the
class of failure that isn't a routine "safety limit says not yet" decision
(that's ordinary data — ``RemediationActionStatus.BLOCKED_BY_SAFETY_LIMIT``
in the audit log, not an exception) but a hard refusal to take an unsafe
action at all, e.g. a dispatched action type the executing side does not
support, or a target that fails a local allowlist check. Kept in
``shared`` rather than ``collector.exceptions`` because both the Collector
(deciding what to dispatch) and the Agent (deciding whether to actually
execute what was dispatched) need to raise it.
"""

from shared.exceptions.base import ClusterPulseError


class RemediationSafetyError(ClusterPulseError):
    """Raised when taking a remediation action would be unsafe.

    Distinct from a routine safety-limit-blocked decision: this signals a
    hard refusal (unsupported action type, target outside an allowlist)
    rather than an expected "try again later" outcome.
    """
