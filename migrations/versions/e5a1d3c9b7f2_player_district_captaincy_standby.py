"""player district, captaincy and stand-by (squad sheet import)

Revision ID: e5a1d3c9b7f2
Revises: c7d2e9a4f1b8
Create Date: 2026-11-14 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1d3c9b7f2'
down_revision: Union[str, Sequence[str], None] = 'c7d2e9a4f1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('players') as b:
        b.add_column(sa.Column('district', sa.String(length=100), nullable=True))
        b.add_column(sa.Column('captaincy', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('standby', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('players') as b:
        b.drop_column('standby')
        b.drop_column('captaincy')
        b.drop_column('district')
