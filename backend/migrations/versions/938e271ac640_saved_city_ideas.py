"""Save requested city activity ideas and bounded search evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '938e271ac640'
down_revision = '6a901b28c314'
branch_labels = None
depends_on = None

def upgrade():
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')
    op.create_table('city_idea_sets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('trip_id', sa.String(36), sa.ForeignKey('trips.id', ondelete='CASCADE'), nullable=False),
        sa.Column('destination_id', sa.String(64), sa.ForeignKey('destinations.id'), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('request_json', json_type, nullable=False),
        sa.Column('result_json', json_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_city_idea_sets_trip_id', 'city_idea_sets', ['trip_id'])
    op.create_index('ix_city_idea_sets_input_hash', 'city_idea_sets', ['input_hash'])
    op.create_table('city_web_cache',
        sa.Column('query_hash', sa.String(64), primary_key=True),
        sa.Column('result_json', json_type, nullable=False),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))

def downgrade():
    op.drop_table('city_web_cache')
    op.drop_index('ix_city_idea_sets_input_hash', table_name='city_idea_sets')
    op.drop_index('ix_city_idea_sets_trip_id', table_name='city_idea_sets')
    op.drop_table('city_idea_sets')
