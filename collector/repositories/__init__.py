"""Data-access layer: Protocols (interfaces) + SQLAlchemy implementations.

Services depend on the Protocols in ``protocols.py``, not on the concrete
SQLAlchemy classes — Dependency Inversion, mirroring how
``agent/scheduler.py`` depends on ``shared.protocols`` rather than concrete
Agent classes.
"""
