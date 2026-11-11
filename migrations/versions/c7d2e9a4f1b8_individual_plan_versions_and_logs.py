"""saved individual plan versions and exercise logs

Revision ID: c7d2e9a4f1b8
Revises: b3f1c7a9e2d4
Create Date: 2026-11-11 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d2e9a4f1b8'
down_revision: Union[str, Sequence[str], None] = 'b3f1c7a9e2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'individual_plan_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=False),
        sa.Column('window', sa.String(length=20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('edits', sa.JSON(), nullable=True),
        sa.Column('based_on', sa.String(length=20), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'season_id', 'version'),
    )
    op.create_index(op.f('ix_individual_plan_versions_player_id'), 'individual_plan_versions', ['player_id'], unique=False)
    op.create_table(
        'plan_exercise_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('plan_version_id', sa.Integer(), nullable=True),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('phase', sa.String(length=20), nullable=False),
        sa.Column('area', sa.String(length=30), nullable=False),
        sa.Column('exercise', sa.String(length=200), nullable=False),
        sa.Column('sets_done', sa.Integer(), nullable=True),
        sa.Column('reps_done', sa.Integer(), nullable=True),
        sa.Column('technique_ok', sa.Boolean(), nullable=False),
        sa.Column('pain', sa.Boolean(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('recorded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['plan_version_id'], ['individual_plan_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recorded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_plan_exercise_logs_player_id'), 'plan_exercise_logs', ['player_id'], unique=False)
    op.create_index(op.f('ix_plan_exercise_logs_log_date'), 'plan_exercise_logs', ['log_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_plan_exercise_logs_log_date'), table_name='plan_exercise_logs')
    op.drop_index(op.f('ix_plan_exercise_logs_player_id'), table_name='plan_exercise_logs')
    op.drop_table('plan_exercise_logs')
    op.drop_index(op.f('ix_individual_plan_versions_player_id'), table_name='individual_plan_versions')
    op.drop_table('individual_plan_versions')
