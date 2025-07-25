"""add reserve fields in deals table

Revision ID: 6fe9f90c60ac
Revises: 7f9d9f3a4ee8
Create Date: 2025-07-22 08:40:48.768764

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fe9f90c60ac'
down_revision: Union[str, None] = '7f9d9f3a4ee8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('deals', sa.Column('is_reserved', sa.Boolean(), nullable=True))
    op.add_column('deals', sa.Column('reservation_amount', sa.Float(), nullable=True))
    op.add_column('deals', sa.Column('reservation_until', sa.DateTime(timezone=True), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('deals', 'reservation_until')
    op.drop_column('deals', 'reservation_amount')
    op.drop_column('deals', 'is_reserved')
    # ### end Alembic commands ###
