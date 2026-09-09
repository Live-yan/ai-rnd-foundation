"""AI R&D workbench: provider registry, clarification state and observable tool stages."""
from alembic import op
import sqlalchemy as sa

revision = "rnd_0002"
down_revision = "rnd_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("rnd_project", sa.Column("clarification_status", sa.String(32), nullable=False, server_default="NEEDS_CLARIFICATION"))
    op.add_column("rnd_project", sa.Column("clarification", sa.JSON(), nullable=True))
    op.add_column("rnd_project", sa.Column("clarification_provider_id", sa.String(36), nullable=True))
    op.add_column("rnd_project", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_rnd_project_clarification_status", "rnd_project", ["clarification_status"])

    op.create_table(
        "rnd_provider_profile",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "name", name="uq_rnd_provider_owner_name"),
    )
    for col in ["owner_id", "provider", "enabled", "is_default"]:
        op.create_index(f"ix_rnd_provider_profile_{col}", "rnd_provider_profile", [col])

    op.add_column("rnd_run", sa.Column("stage_details", sa.JSON(), nullable=True))
    op.add_column("rnd_event", sa.Column("stage", sa.String(40), nullable=True))
    op.add_column("rnd_event", sa.Column("tool", sa.String(40), nullable=True))
    op.add_column("rnd_event", sa.Column("payload", sa.JSON(), nullable=True))
    op.create_index("ix_rnd_event_stage", "rnd_event", ["stage"])


def downgrade():
    op.drop_index("ix_rnd_event_stage", table_name="rnd_event")
    for col in ["payload", "tool", "stage"]:
        op.drop_column("rnd_event", col)
    op.drop_column("rnd_run", "stage_details")
    for col in ["is_default", "enabled", "provider", "owner_id"]:
        op.drop_index(f"ix_rnd_provider_profile_{col}", table_name="rnd_provider_profile")
    op.drop_table("rnd_provider_profile")
    op.drop_index("ix_rnd_project_clarification_status", table_name="rnd_project")
    for col in ["updated_at", "clarification_provider_id", "clarification", "clarification_status"]:
        op.drop_column("rnd_project", col)
