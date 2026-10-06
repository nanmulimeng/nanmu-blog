"""engine 测试公共夹具。

Task 0 声明占位(Task 3 起逐步填充):
- tmp_engine_db:临时 engine.db 连接(已迁移,Task 3 实现)
- fake_llm:替身 LLM(零网络零付费,后续任务填充)
"""

import pytest

from nanmu_engine.db import connect_db, migrate


@pytest.fixture
def tmp_engine_db(tmp_path):
    """临时 engine.db 连接(12 表已迁移,pay_paused=0)。"""
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def fake_llm():
    """替身 LLM(零网络零付费)。后续任务实现。"""
    raise NotImplementedError("fake_llm 由后续任务填充")


@pytest.fixture
def fake_llm():
    """替身 LLM(零网络零付费)。后续任务实现。"""
    raise NotImplementedError("fake_llm 由后续任务填充")
