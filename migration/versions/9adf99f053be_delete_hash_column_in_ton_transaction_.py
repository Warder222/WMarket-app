"""delete hash column in ton_transaction_history table

Revision ID: 9adf99f053be
Revises: 1586f2edc7b9
Create Date: 2025-07-11 09:46:08.557772

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9adf99f053be'
down_revision: Union[str, None] = '1586f2edc7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('ton_transactions', 'tx_hash')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('ton_transactions', sa.Column('tx_hash', sa.VARCHAR(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###
