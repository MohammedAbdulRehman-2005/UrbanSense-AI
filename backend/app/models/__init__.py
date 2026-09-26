# Import all models so Alembic can discover them
from backend.app.models.road_segment import RoadSegment
from backend.app.models.observation import ObservationModel
from backend.app.models.opportunity import OpportunityModel
from backend.app.models.event import EventModel
from backend.app.models.roadtwin import RoadTwinStateModel
from backend.app.models.evidence import EvidenceModel
from backend.app.models.authority_action import AuthorityActionModel
from backend.app.models.traffic import TrafficObservationModel, TrafficBottleneckModel

__all__ = [
    "RoadSegment",
    "ObservationModel",
    "OpportunityModel",
    "EventModel",
    "RoadTwinStateModel",
    "EvidenceModel",
    "AuthorityActionModel",
    "TrafficObservationModel",
    "TrafficBottleneckModel",
]
