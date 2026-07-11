"""Node registry read endpoints."""

from fastapi import APIRouter, Depends

from collector.api.deps import get_node_registry_service, verify_api_token
from collector.api.schemas import NodeRead
from collector.services.node_registry import NodeRegistryService

router = APIRouter(dependencies=[Depends(verify_api_token)])


@router.get("/api/v1/nodes", response_model=list[NodeRead])
def list_nodes(
    service: NodeRegistryService = Depends(get_node_registry_service),
) -> list[NodeRead]:
    """List every node the Collector has heard from."""
    return [NodeRead.from_view(view) for view in service.list_nodes()]


@router.get("/api/v1/nodes/{node_id}", response_model=NodeRead)
def get_node(
    node_id: str, service: NodeRegistryService = Depends(get_node_registry_service)
) -> NodeRead:
    """Get a single node's registry entry (404 if never seen)."""
    return NodeRead.from_view(service.get_node(node_id))
