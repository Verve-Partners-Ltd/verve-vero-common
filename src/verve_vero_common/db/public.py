"""
Public/Control Plane Database Session

Provides database access to the shared control plane database.
Use this for:
- Portal registry (portals, domains, SSO config)
- Auth infrastructure (auth_codes, refresh_tokens)
- Provisioning jobs
- Any cross-portal admin operations

Usage:
------
    from verve_vero_common.db import get_public_db
    from sqlalchemy.orm import Session

    # As FastAPI dependency
    @app.get("/portals")
    def list_portals(db: Session = Depends(get_public_db)):
        return db.query(Portal).all()

    # Direct usage
    for db in get_public_db():
        portals = db.query(Portal).all()
"""

from typing import Generator, Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

# Module-level engine (initialized on first use or via init_public_db)
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def init_public_db(database_url: str, **engine_kwargs) -> Engine:
    """
    Initialize the public database engine.

    Call this on application startup if you need custom engine configuration.
    If not called, the engine will be created lazily on first use.

    Args:
        database_url: PostgreSQL connection URL
        **engine_kwargs: Additional arguments passed to create_engine
                        (pool_size, max_overflow, pool_pre_ping, etc.)

    Returns:
        The created SQLAlchemy Engine
    """
    global _engine, _SessionLocal

    default_kwargs = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
    }
    default_kwargs.update(engine_kwargs)

    _engine = create_engine(database_url, **default_kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    return _engine


def get_public_engine() -> Engine:
    """
    Get the public database engine.

    Returns:
        The SQLAlchemy Engine for the public database

    Raises:
        RuntimeError: If the engine hasn't been initialized
    """
    if _engine is None:
        raise RuntimeError(
            "Public database not initialized. "
            "Call init_public_db(DATABASE_URL) on startup."
        )
    return _engine


def get_public_db() -> Generator[Session, None, None]:
    """
    Get a database session for the public/control plane database.

    This is a FastAPI-compatible dependency that yields a session
    and handles commit/rollback/close automatically.

    Usage:
        @app.get("/portals")
        def list_portals(db: Session = Depends(get_public_db)):
            return db.query(Portal).all()

    Yields:
        SQLAlchemy Session connected to the public database
    """
    if _SessionLocal is None:
        raise RuntimeError(
            "Public database not initialized. "
            "Call init_public_db(DATABASE_URL) on startup."
        )

    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class PublicSession:
    """
    Context manager for public database sessions.

    Use this for non-FastAPI code that needs control plane access.

    Usage:
        with PublicSession() as db:
            portals = db.query(Portal).all()
        # Transaction auto-commits on exit
    """

    def __init__(self):
        self.db: Optional[Session] = None

    def __enter__(self) -> Session:
        if _SessionLocal is None:
            raise RuntimeError(
                "Public database not initialized. "
                "Call init_public_db(DATABASE_URL) on startup."
            )
        self.db = _SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
            self.db.close()
        return False
