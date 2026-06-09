import pytest

import db as db_module


@pytest.fixture()
def conn():
    c = db_module.connect(":memory:")
    db_module.init_db(c)
    yield c
    c.close()
