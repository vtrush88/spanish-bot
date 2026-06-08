def test_python_imports_work():
    import sqlite3
    import asyncio  # noqa: F401
    assert sqlite3.sqlite_version_info >= (3, 0, 0)
