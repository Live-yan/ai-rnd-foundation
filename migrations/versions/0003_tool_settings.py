"""Encrypted administrator tool settings; no destructive changes to projects."""
from alembic import op
import sqlalchemy as sa
revision = "rnd_0003"
down_revision = "rnd_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("rnd_tool_setting", sa.Column("id", sa.String(40), primary_key=True),
                    sa.Column("revision", sa.Integer(), nullable=False),
                    sa.Column("ciphertext", sa.Text(), nullable=False),
                    sa.Column("web_url", sa.String(1024), nullable=False, server_default=""))


def downgrade():
    op.drop_table("rnd_tool_setting")
