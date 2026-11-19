"""Athlete seasonal plan: STEP 0 answers per player and season

Revision ID: a7c3e1f9d2b5
Revises: f3b8c1d2a6e4
Create Date: 2026-11-16 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c3e1f9d2b5'
down_revision: Union[str, Sequence[str], None] = 'f3b8c1d2a6e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'athlete_plan_inputs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('season_id', sa.Integer(), sa.ForeignKey('seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', sa.Integer(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('answers', sa.JSON(), nullable=False),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('season_id', 'player_id'),
    )
    op.create_index('ix_athlete_plan_inputs_season_id', 'athlete_plan_inputs', ['season_id'])


def downgrade() -> None:
    op.drop_index('ix_athlete_plan_inputs_season_id', table_name='athlete_plan_inputs')
    op.drop_table('athlete_plan_inputs')
