from alembic import context
from factory.config import get_settings
from factory.database import Base, Database

db = Database(get_settings().database_url)
with db.engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, version_table='rnd_alembic_version')
    with context.begin_transaction():
        context.run_migrations()
