"""self sign-up with administrator approval

Revision ID: b3f1c7a9e2d4
Revises: 2458cef34f8b
Create Date: 2026-11-11 10:00:00.000000

Existing users are marked approved, so nobody loses access.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1c7a9e2d4'
down_revision: Union[str, Sequence[str], None] = '2458cef34f8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users') as b:          # batch mode: SQLite cannot add a foreign key with ALTER TABLE
        b.add_column(sa.Column('approval_status', sa.Enum('pending', 'approved', 'rejected', name='approvalstatus',
                                                          native_enum=False, length=32),
                               nullable=False, server_default='approved'))
        b.add_column(sa.Column('signup_note', sa.String(length=300), nullable=True))
        b.add_column(sa.Column('reviewed_by', sa.Integer(), nullable=True))
        b.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        b.create_foreign_key('fk_users_reviewed_by_users', 'users', ['reviewed_by'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('users') as b:
        b.drop_constraint('fk_users_reviewed_by_users', type_='foreignkey')
        b.drop_column('reviewed_at')
        b.drop_column('reviewed_by')
        b.drop_column('signup_note')
        b.drop_column('approval_status')
