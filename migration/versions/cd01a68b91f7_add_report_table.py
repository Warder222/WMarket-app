"""add report table

Revision ID: cd01a68b91f7
Revises: 75c072ce7cfb
Create Date: 2025-06-24 09:20:31.688535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd01a68b91f7'
down_revision: Union[str, None] = '75c072ce7cfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('chat_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.Integer(), nullable=True),
    sa.Column('reporter_id', sa.BigInteger(), nullable=True),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('resolved', sa.Boolean(), nullable=True),
    sa.Column('admin_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['admin_id'], ['users.tg_id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['chat_id'], ['chats.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.tg_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('chat_reports')
    # ### end Alembic commands ###
