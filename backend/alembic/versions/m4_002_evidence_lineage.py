"""
UrbanSense AI — M4 Evidence Lineage & Persistence Migration
============================================================
Adds:
    - latitude (Float, nullable=True)
    - longitude (Float, nullable=True)
    - sensing_pass_id (String, nullable=True)
    - trace_id (String, nullable=True)
to the 'evidence' table.

Revises: m4_001_maintenance
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "m4_002_evidence_lineage"
down_revision = "m4_001_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("evidence", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("evidence", sa.Column("sensing_pass_id", sa.String(), nullable=True))
    op.add_column("evidence", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("ix_evidence_sensing_pass_id", "evidence", ["sensing_pass_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_sensing_pass_id", table_name="evidence")
    op.drop_column("evidence", "trace_id")
    op.drop_column("evidence", "sensing_pass_id")
    op.drop_column("evidence", "longitude")
    op.drop_column("evidence", "latitude")
