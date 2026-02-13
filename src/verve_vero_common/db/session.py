"""
Multi-database Session Management for Portal Isolation

Each portal has its own database, providing complete data isolation.

Transaction Handling:
--------------------
Sessions use autocommit=False (SQLAlchemy default). This means:
- Changes are NOT auto-committed
- On success: call db.commit() explicitly, or let the request complete normally
- On exception: changes are automatically rolled back when session closes
- This is safer - partial failures don't leave inconsistent data

Usage:
------
    # In FastAPI route handlers (simple read)
    @app.get("/agents")
    def list_agents(db: Session = Depends(get_portal_db)):
        return db.query(Agent).all()  # No commit needed for reads

    # For writes - commit explicitly
    @app.post("/agents")
    def create_agent(data: AgentCreate, db: Session = Depends(get_portal_db)):
        agent = Agent(**data.dict())
        db.add(agent)
        db.commit()  # Explicit commit
        db.refresh(agent)
        return agent

    # For background jobs
    with PortalSession("portal_acme") as db:
        db.add(item)
        db.commit()  # Explicit commit
"""

from functools import lru_cache
from typing import Generator, Optional, Callable
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from verve_vero_common.db.portal import get_current_portal

# Type for database URL resolver function
DatabaseUrlResolver = Callable[[str], Optional[str]]

# Module-level resolver (set during initialization)
_get_portal_database_url: Optional[DatabaseUrlResolver] = None


def init_portal_db(get_portal_database_url: DatabaseUrlResolver) -> None:
    """
    Initialize portal database session management.

    Call this on application startup with a function that resolves
    portal IDs to database URLs.
    """
    global _get_portal_database_url
    _get_portal_database_url = get_portal_database_url


@lru_cache(maxsize=100)
def get_engine_for_portal(portal_id: str) -> Engine:
    """
    Get or create a cached database engine for a specific portal.

    Each portal has its own database, so we create and cache engines
    per portal. The LRU cache prevents creating too many engines while
    keeping frequently used portal connections ready.
    """
    if _get_portal_database_url is None:
        raise RuntimeError(
            "Portal database not initialized. "
            "Call init_portal_db(url_resolver) on startup."
        )

    db_url = _get_portal_database_url(portal_id)
    if not db_url:
        raise ValueError(f"No database configured for portal: {portal_id}")

    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_portal_db() -> Generator[Session, None, None]:
    """
    Get a database session for the current portal.

    Uses the portal ID from the request context (set by middleware).
    Caller is responsible for calling db.commit() for write operations.

    Yields:
        SQLAlchemy Session for the current portal's database
    """
    portal_id = get_current_portal()
    if not portal_id:
        raise RuntimeError(
            "No portal context set. Ensure middleware calls set_current_portal()."
        )

    engine = get_engine_for_portal(portal_id)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_for_portal(portal_id: str) -> Generator[Session, None, None]:
    """
    Get a database session for a specific portal.

    Use this for background jobs or admin operations where
    the portal context is not set via middleware.
    Caller is responsible for calling db.commit() for write operations.
    """
    engine = get_engine_for_portal(portal_id)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class PortalSession:
    """
    Context manager for portal-scoped database sessions.

    Use this for non-FastAPI code that needs to access portal data.
    Caller is responsible for calling db.commit() for write operations.

    Usage:
        with PortalSession("portal_acme") as db:
            db.add(item)
            db.commit()  # Explicit commit
    """

    def __init__(self, portal_id: str):
        self.portal_id = portal_id
        self.db: Optional[Session] = None

    def __enter__(self) -> Session:
        engine = get_engine_for_portal(self.portal_id)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.db:
            self.db.close()
        return False


def clear_engine_cache() -> None:
    """
    Clear the cached database engines.
    Call this when portal database configurations change.
    """
    get_engine_for_portal.cache_clear()
