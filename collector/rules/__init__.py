"""The Rule Engine: evaluates configured Threshold and Rate-of-change rules
against freshly-ingested metric samples. Rules are static and config-file
driven — see ``docs/adr/006-alert-lifecycle.md`` for why, not a dynamic
database-backed rule-management API.
"""
