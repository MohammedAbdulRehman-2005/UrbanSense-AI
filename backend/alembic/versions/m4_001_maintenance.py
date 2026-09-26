"""
UrbanSense AI — M4 Maintenance Lifecycle migration
===================================================
Creates: authority_actions table
Adds indexes on roadtwin_states for maintenance lifecycle fields.

Revision ID: m4_001_maintenance
Revises: m3_001_evidence
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "m4_001_maintenance"
down_revision = "m3_001_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Create authority_actions table ---
    op.create_table(
        "authority_actions",
        sa.Column("action_id", sa.String(), primary_key=True),
        sa.Column("road_segment_id", sa.String(), nullable=False),
        sa.Column("roadtwin_id", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("work_order_id", sa.String(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prior_roadtwin_state", sa.String(), nullable=False),
        sa.Column("resulting_roadtwin_state", sa.String(), nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_authority_actions_road_segment_id", "authority_actions", ["road_segment_id"])
    op.create_index("ix_authority_actions_roadtwin_id", "authority_actions", ["roadtwin_id"])
    op.create_index("ix_authority_actions_action_type", "authority_actions", ["action_type"])


def downgrade() -> None:
    op.drop_index("ix_authority_actions_action_type", table_name="authority_actions")
    op.drop_index("ix_authority_actions_roadtwin_id", table_name="authority_actions")
    op.drop_index("ix_authority_actions_road_segment_id", table_name="authority_actions")
    op.drop_table("authority_actions")
