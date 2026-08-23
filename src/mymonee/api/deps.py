from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from mymonee.config import Settings, get_settings
from mymonee.db.session import get_session_factory


def settings_dep(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    return settings if isinstance(settings, Settings) else get_settings()


def db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Depends(db_session)
SettingsDep = Depends(settings_dep)
