"""engine 测试公共夹具。

Task 0 仅声明占位(计划 Task 0 Step 3:占位是 fixture 声明,不是设计占位):
- tmp_engine_db:Task 3 填充(connect_db + migrate 的临时 SQLite 库)
- fake_llm:后续任务复用的替身 LLM fixture
"""

import pytest


@pytest.fixture
def tmp_engine_db():
    """临时 engine.db 连接(已迁移)。Task 3 实现。"""
    raise NotImplementedError("tmp_engine_db 由 Task 3 填充")


@pytest.fixture
def fake_llm():
    """替身 LLM(零网络零付费)。后续任务实现。"""
    raise NotImplementedError("fake_llm 由后续任务填充")
