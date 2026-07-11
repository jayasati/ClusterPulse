# ClusterPulse

ClusterPulse is a monitoring and observability toolkit for Nutanix clusters. It collects
cluster health, performance, and capacity metrics via a lightweight collector, ships them
through an agent layer, and surfaces them for alerting and analysis.

## Repository layout

```
agent/       Runtime agent that receives, processes, and forwards collected data
collector/   Data collectors that poll Nutanix cluster APIs for metrics/health
shared/      Shared libraries/types/utilities used by agent and collector
infra/       Infrastructure-as-code and deployment configuration
scripts/     One-off and operational scripts
docs/        Project documentation
tests/       Test suites
docker/      Dockerfiles and container-related assets
```

## Getting started

```bash
make setup
make test
```

See `.claude/PROJECT.md` for project context and `.claude/ROADMAP.md` for planned work.

## License

See [LICENSE](LICENSE).
