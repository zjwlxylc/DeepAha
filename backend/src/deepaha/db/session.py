from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from deepaha.core.settings import Settings, get_settings


def get_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    if resolved_settings.database_url is None:
        raise ValueError("DEEPAHA_DATABASE_URL is required to create a database engine")
    return create_engine(resolved_settings.database_url, pool_pre_ping=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
