"""Workload: heart rate (TRIMP) and external load fields; players' max and resting heart rate

Revision ID: b8d4f2a6c9e1
Revises: a7c3e1f9d2b5
Create Date: 2026-11-22 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d4f2a6c9e1'
down_revision: Union[str, Sequence[str], None] = 'a7c3e1f9d2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOG_COLUMNS = [
    ('hr_avg', sa.Integer()), ('zone_minutes', sa.JSON()), ('hit_minutes', sa.Float()), ('sprint_m', sa.Integer()),
    ('volume_load_kg', sa.Float()), ('foot_contacts', sa.Integer()), ('sprint_times', sa.JSON()),
]


def upgrade() -> None:
    with op.batch_alter_table('workload_logs') as b:
        for name, kind in LOG_COLUMNS:
            b.add_column(sa.Column(name, kind, nullable=True))
    with op.batch_alter_table('players') as b:
        b.add_column(sa.Column('hr_max', sa.Integer(), nullable=True))
        b.add_column(sa.Column('hr_rest', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('players') as b:
        b.drop_column('hr_rest')
        b.drop_column('hr_max')
    with op.batch_alter_table('workload_logs') as b:
        for name, _ in reversed(LOG_COLUMNS):
            b.drop_column(name)
