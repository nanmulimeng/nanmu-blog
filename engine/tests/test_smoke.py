"""工程冒烟:包可安装可导入(Task 0 Step 3)。"""


def test_package_importable():
    import nanmu_engine

    assert nanmu_engine is not None
