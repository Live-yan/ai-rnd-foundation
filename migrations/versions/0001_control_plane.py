"""Initial control-plane schema, frozen for repeatable deployment."""
from alembic import op
import sqlalchemy as sa
revision = 'rnd_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rnd_project',
        sa.Column('id',sa.String(36),primary_key=True), sa.Column('owner_id',sa.String(80),nullable=False),
        sa.Column('title',sa.String(100),nullable=False), sa.Column('template_id',sa.String(80),nullable=False),
        sa.Column('messages',sa.JSON(),nullable=False), sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_rnd_project_owner_id','rnd_project',['owner_id'])
    op.create_table('rnd_run',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('project_id',sa.String(36),sa.ForeignKey('rnd_project.id'),nullable=False),
        sa.Column('owner_id',sa.String(80),nullable=False), sa.Column('idempotency_key',sa.String(100),nullable=False),
        sa.Column('request',sa.JSON(),nullable=False), sa.Column('status',sa.String(32),nullable=False),
        sa.Column('spec',sa.JSON(),nullable=True), sa.Column('spec_digest',sa.String(64),nullable=True),
        sa.Column('decision',sa.JSON(),nullable=True), sa.Column('artifact',sa.Text(),nullable=True),
        sa.Column('artifact_sha256',sa.String(64),nullable=True), sa.Column('checks',sa.JSON(),nullable=True),
        sa.Column('error',sa.Text(),nullable=True), sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('owner_id','idempotency_key',name='uq_rnd_run_idempotency'))
    for col in ['project_id','owner_id','status']:
        op.create_index('ix_rnd_run_' + col,'rnd_run',[col])
    op.create_table('rnd_event',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('rnd_run.id'),nullable=False),
        sa.Column('level',sa.String(16),nullable=False),sa.Column('message',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_rnd_event_run_id','rnd_event',['run_id'])
    op.create_table('rnd_outbox',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('rnd_run.id'),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),sa.Column('sent',sa.Boolean(),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('error',sa.Text(),nullable=True),
        sa.UniqueConstraint('run_id','kind',name='uq_rnd_outbox_kind'))
    op.create_index('ix_rnd_outbox_run_id','rnd_outbox',['run_id'])
    op.create_index('ix_rnd_outbox_sent','rnd_outbox',['sent'])


def downgrade():
    for table in ['rnd_outbox','rnd_event','rnd_run','rnd_project']:
        op.drop_table(table)
