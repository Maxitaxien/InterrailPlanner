"""Persist on-demand timetable research, separately from bookings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '6a901b28c314'
down_revision = 'b22403466dca'
branch_labels = None
depends_on = None

def upgrade():
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')
    op.create_table('rail_journey_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('origin_id', sa.String(64), sa.ForeignKey('destinations.id'), nullable=False),
        sa.Column('destination_id', sa.String(64), sa.ForeignKey('destinations.id'), nullable=False),
        sa.Column('journey_json', json_type, nullable=False),
        sa.Column('sources_json', json_type, nullable=False),
        sa.Column('queried_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_rail_journey_snapshots_expires_at', 'rail_journey_snapshots', ['expires_at'])

def downgrade():
    op.drop_index('ix_rail_journey_snapshots_expires_at', table_name='rail_journey_snapshots')
    op.drop_table('rail_journey_snapshots')
