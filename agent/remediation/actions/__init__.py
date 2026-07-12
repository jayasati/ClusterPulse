"""Individual remediation action handlers.

Each handler raises (``shared.exceptions.RemediationSafetyError`` for a
refusal, ``OSError`` for an execution failure) rather than catching its own
errors — ``agent/remediation/executor.py`` is the single place that turns a
raised exception into a ``FAILED`` ``ActionResult``.
"""
