from alembic import context
from sqlalchemy import create_engine
from app.core.config import get_settings
from app.core.database import Base
from app.models import entities, integrations  # register all schema metadata

config = context.config

def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        migrate(connection)
