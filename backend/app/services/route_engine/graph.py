import networkx as nx
from app.services.errors import PlanningError
from app.services.endpoint_transfers import endpoint_transfers
from sqlalchemy import select
from app.models.entities import Destination, RailConnection

class RailGraph:
    def __init__(self, db):
        self.destinations = {d.id: d for d in db.scalars(select(Destination)).all()}
        self._paths = {}
        self.graph = nx.MultiDiGraph()
        self.graph.add_nodes_from(self.destinations)
        for edge in db.scalars(select(RailConnection)).all():
            self.graph.add_edge(edge.origin_id, edge.destination_id, key=edge.id,
                minutes=edge.estimated_minutes, connection_id=edge.id,
                mode="rail",
                night_train=edge.night_train, source=edge.source,
                transfers=edge.transfers, service_type=edge.service_type, estimate_quality=edge.estimate_quality,
                reviewed_at=edge.reviewed_at.isoformat() if edge.reviewed_at else None, reservation_warning=edge.reservation_warning)
        for edge in endpoint_transfers(self.destinations):
            values = {**edge, "minutes": edge["estimated_minutes"], "connection_id": edge["id"]}
            self.graph.add_edge(edge["origin_id"], edge["destination_id"], key=edge["id"], **values)

    def segment_graph(self, allow_endpoint_transfer=True):
        return nx.subgraph_view(self.graph, filter_edge=lambda a,b,k: not self.graph[a][b][k].get("night_train") and (allow_endpoint_transfer or self.graph[a][b][k].get("mode", "rail") == "rail"))

    def path(self, origin, destination, allow_endpoint_transfer=True):
        key = (origin, destination, allow_endpoint_transfer)
        if key not in self._paths:
            self._paths[key] = nx.shortest_path(self.segment_graph(allow_endpoint_transfer), origin, destination, weight="minutes")
        return self._paths[key]

    def rail_reachable(self):
        if not hasattr(self, "_rail_reachable"):
            self._rail_reachable = nx.descendants(self.segment_graph(False), "oslo") | {"oslo"}
        return self._rail_reachable

    def daytime(self):
        bounded = object.__new__(RailGraph)
        bounded.destinations = self.destinations
        bounded._paths = {}
        bounded.graph = self.segment_graph()
        return bounded

    def limited(self, _max_minutes):
        # Compatibility for older callers: daily limits are deliberately ignored.
        return self.daytime()

    def connection_error(self, origin, destination):
        names = f"{self.destinations[origin].name} → {self.destinations[destination].name}"
        return PlanningError("ROUTE_NOT_FOUND", f"Our catalog has no supported connection for {names}. This is a data-coverage limitation, not confirmation that the real journey is impossible. Only explicitly modeled endpoint ferry/ground transfers are available; other gaps and overnight trains still need research.", {"origin": origin, "destination": destination})

    def edge(self, origin, destination):
        return min(self.graph[origin][destination].values(), key=lambda e: e["minutes"])
