-- Read-only role for Grafana's PostgreSQL datasource.
--
-- Grafana never needs (and therefore never gets) write access: a
-- compromised or misconfigured dashboard can read monitoring data but can
-- never mutate alerts, audit rows, or the node registry.
--
-- Runs automatically on first `docker compose up` (docker-entrypoint-initdb.d);
-- for systemd installs, deploy/install_collector.sh applies the same
-- statements via psql.

CREATE ROLE clusterpulse_ro WITH LOGIN PASSWORD 'clusterpulse_ro';
GRANT CONNECT ON DATABASE clusterpulse TO clusterpulse_ro;
GRANT USAGE ON SCHEMA public TO clusterpulse_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO clusterpulse_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO clusterpulse_ro;
