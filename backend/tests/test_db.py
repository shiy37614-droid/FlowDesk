
from sqlalchemy import text

from app.db.session import engine


def test_mysql_connection():
    with engine.connect() as connection:

        result = connection.execute(
            text("SELECT 1")
        ).scalar_one()

        database = connection.execute(
            text("SELECT DATABASE()")
        ).scalar_one()

        timezone = connection.execute(
            text("SELECT @@session.time_zone")
        ).scalar_one()

    assert result == 1
    assert database == "flowdesk_init_test"
    assert timezone == "+00:00"
