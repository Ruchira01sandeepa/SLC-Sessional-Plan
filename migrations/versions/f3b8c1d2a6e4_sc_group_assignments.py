"""S&C group assignments (a coach's move of a player to another group)

Revision ID: f3b8c1d2a6e4
Revises: e5a1d3c9b7f2
Create Date: 2026-11-15 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b8c1d2a6e4'
down_revision: Union[str, Sequence[str], None] = 'e5a1d3c9b7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sc_group_assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('area', sa.String(length=30), nullable=False),
        sa.Column('set_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('set_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('season_id', 'player_id'),
    )
    op.create_index('ix_sc_group_assignments_season_id', 'sc_group_assignments', ['season_id'])


def downgrade() -> None:
    op.drop_index('ix_sc_group_assignments_season_id', table_name='sc_group_assignments')
    op.drop_table('sc_group_assignments')
