"""Agent-side execution of dispatched remediation actions.

Two independent opt-ins gate real execution: the Collector's own
``remediation_enabled`` (whether to dispatch at all) and this Agent's own
``remediation_enabled`` (whether to act on what it receives) — see
``docs/adr/007-remediation-safety.md``. ``PlaybookExecutor``
(``executor.py``) is the single place that catches failures and turns them
into an ``ActionResult``; the individual action handlers in ``actions/``
raise rather than swallow, so that error handling isn't duplicated per
action.
"""
