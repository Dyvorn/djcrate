import pytest
from djcrate.database import Base, init_db, get_db_connection

TEST_DB = ":memory:"

@pytest.fixture(scope="session")
def db_engine():
    """
    Session-scoped fixture to initialize the in-memory SQLite database engine.
    Uses StaticPool under the hood so all connections share the same memory instance.
    """
    return init_db(TEST_DB)

@pytest.fixture(autouse=True)
def db_setup(db_engine):
    """
    Autouse fixture that runs for every test.
    Guarantees test isolation by dropping and re-creating all tables before and after each test.
    """
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    yield
    Base.metadata.drop_all(bind=db_engine)

@pytest.fixture
def db_session(db_setup):
    """
    Provides a clean SQLAlchemy Session context for tests requiring direct database queries.
    """
    with get_db_connection(TEST_DB) as session:
        yield session
