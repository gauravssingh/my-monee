"""CLI: repair swapped transaction dates."""

from __future__ import annotations

import json
import logging

from mymonee.config import reload_settings
from mymonee.db.session import get_session_factory, init_db
from mymonee.logging_setup import setup_logging
from mymonee.services.date_repair import repair_swapped_transaction_dates


def main() -> int:
    settings = reload_settings()
    setup_logging(settings)
    init_db(settings)
    session = get_session_factory()()
    try:
        fixed = repair_swapped_transaction_dates(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(json.dumps({"fixed": fixed}))
    logging.getLogger("mymonee").info("Repaired %s transaction dates", fixed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
