import pytest
from sqlalchemy.orm import sessionmaker

import food_recognition.db as db


@pytest.fixture(autouse=True, scope="session")
def _synced_schema():
    """Make sure every table (incl. meal_schedule) exists before any test runs.

    db.sync_schema() issues CREATE TABLE / DROP TRIGGER statements, which
    MySQL always auto-commits — that can't be wrapped in the SAVEPOINT/rollback
    trick below, so it intentionally runs once, outside of it. It's safe to
    call repeatedly: create_all() and the seed helpers are no-ops once the
    tables exist and are populated.
    """
    db.sync_schema()


@pytest.fixture(autouse=True)
def db_transaction(monkeypatch):
    """Run each test inside a single DB transaction that is always rolled back.

    db.py functions each open their own Session and call session.commit().
    Binding those sessions to one externally-owned Connection with
    join_transaction_mode="create_savepoint" makes every internal commit()
    release a SAVEPOINT instead of the real transaction, so nothing survives
    once the outer transaction started here is rolled back at teardown.
    This lets db tests hit the real database without leaving any trace.
    """
    connection = db._engine.connect()
    transaction = connection.begin()
    test_session_factory = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint"
    )
    monkeypatch.setattr(db, "_SessionFactory", test_session_factory)

    yield

    transaction.rollback()
    connection.close()
