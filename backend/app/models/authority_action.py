"""
UrbanSense AI — AuthorityAction ORM Model (Milestone 4)
=======================================================
Records maintenance lifecycle actions taken by authorities/contractors.

OWNERSHIP RULES (DO NOT VIOLATE):
- RoadTwin state transitions are ONLY computed in backend/app/roadtwin/engine.py
- evidence_weight is ONLY computed in backend/app/fusion/engine.py
- This model stores lifecycle action records — it does NOT contain transition logic.

REPAIR VERIFICATION RULE:
- A completed maintenance action is NOT proof of repair.
- Repair is only VERIFIED by subsequent independent negative sensing evidence.
- The state machine enforces this: REPAIR_REPORTED → VERIFICATION_PENDING
  (negative evidence required to reach VERIFIED_REPAIRED).

Roles (conceptual — full RBAC is DECISION_REQUIRED / DECISION-007):
    CITIZEN     — can submit observation events
    INSPECTOR   — can dispatch maintenance
    CITY_ENGINEER — can review lifecycle; overrides
    CONTRACTOR  — can report completion of maintenance work

These roles are conceptual for M4 demonstration scope.
Production identity is DECISION-007 (OPEN).
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, Text

from backend.app.db.base import Base


class AuthorityActionModel(Base):
    """
    Append-only record of an authority action in the maintenance lifecycle.

    Each row = one discrete action event.
    Multiple actions may reference the same roadtwin_id (e.g., dispatch + completion).
    """
    __tablename__ = "authority_actions"

    action_id = Column(String, primary_key=True)

    # What road segment / RoadTwin this action targets
    road_segment_id = Column(String, nullable=False, index=True)
    roadtwin_id = Column(String, nullable=False, index=True)

    # Action type:
    #   MAINTENANCE_DISPATCHED — authority scheduled a maintenance crew
    #   REPAIR_COMPLETION_REPORTED — contractor reports work done
    action_type = Column(String, nullable=False)  # MAINTENANCE_DISPATCHED | REPAIR_COMPLETION_REPORTED

    # Who performed this action (conceptual role — DECISION-007 for production RBAC)
    actor_role = Column(String, nullable=False)   # INSPECTOR | CITY_ENGINEER | CONTRACTOR | SYSTEM
    actor_id = Column(String, nullable=False)     # opaque identifier (user ID placeholder)

    # Optional notes / work order reference
    notes = Column(Text, nullable=True)
    work_order_id = Column(String, nullable=True)

    # For MAINTENANCE_DISPATCHED: scheduled visit time
    scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # For REPAIR_COMPLETION_REPORTED: claimed completion time (self-reported)
    claimed_completion_at = Column(DateTime(timezone=True), nullable=True)

    # Trigger: previous RoadTwin state before this action
    prior_roadtwin_state = Column(String, nullable=False)

    # Resulting RoadTwin state after this action
    resulting_roadtwin_state = Column(String, nullable=False)

    # Trace
    trace_id = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
