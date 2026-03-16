from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.config.settings import Settings
from core.persistence.base import Base


def build_engine(settings: Settings) -> Engine:
    database_url = settings.sqlalchemy_database_url
    if database_url.startswith("postgresql+psycopg://"):
        try:
            __import__("psycopg")
        except ImportError:
            database_url = f"sqlite+pysqlite:///{settings.storage_root / 'opsfoundry-local.db'}"

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
