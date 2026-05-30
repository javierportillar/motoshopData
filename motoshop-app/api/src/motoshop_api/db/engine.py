"""Factory de engine SQLAlchemy para MySQL (MyISAM, charset utf8)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

_engine: Engine | None = None
_writer_engine: Engine | None = None


def get_engine(database_url: str | None = None) -> Engine:
    """Retorna un engine singleton con pool_pre_ping habilitado.

    MyISAM no soporta transacciones, así que autocommit está habilitado.
    """
    global _engine
    if _engine is None:
        if database_url is None:
            from motoshop_api.config import settings

            database_url = settings.database_url
        _engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"autocommit": True},
        )
    return _engine


def get_writer_engine() -> Engine:
    """Engine separado para escritura a tablas app_* con usuario app_writer.

    InnoDB sí soporta transacciones, pero mantenemos autocommit para
    compatibilidad con el patrón actual. Cada INSERT es atómico.
    """
    global _writer_engine
    if _writer_engine is None:
        from motoshop_api.config import settings

        _writer_engine = create_engine(
            settings.writer_database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=4,
            connect_args={"autocommit": True},
        )
    return _writer_engine


def reset_engine() -> None:
    """Reset para tests."""
    global _engine, _writer_engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
    if _writer_engine is not None:
        _writer_engine.dispose()
        _writer_engine = None
