"""测试环境隔离守卫 —— 防止测试脚本误写真实用户数据。

背景：开发期用临时脚本做 GUI 自测时，曾忘记设置 ``APPDATA``，
导致测试课程被写进 ``%APPDATA%\\CampusPlanner\\data.json``（真实用户数据）。
这里把「测试必须走沙箱」固化成可执行断言，任何人再写类似脚本都会立刻失败。
"""
from __future__ import annotations

import os
import unittest

from campus_planner import core


class IsolationGuardTest(unittest.TestCase):
    """任何依赖 core.data_dir() 的脚本都必须先把 APPDATA 指到临时目录。"""

    def test_appdata_is_sandboxed_during_tests(self):
        appdata = os.environ.get("APPDATA")
        self.assertTrue(appdata, "测试进程没有 APPDATA，数据会写到默认位置")
        resolved = core.data_dir().resolve()
        repo = core.data_dir().resolve().anchor
        self.assertIn("_gui_appdata", str(resolved).lower(),
                      f"测试期 data_dir() 未指向沙箱：{resolved}")

    def test_sandbox_dir_is_inside_repo_tests(self):
        resolved = core.data_dir().resolve()
        self.assertTrue(resolved.exists() or resolved.parent.exists(),
                        f"沙箱目录不可用：{resolved}")
        self.assertNotIn("Roaming\\\\CampusPlanner", str(resolved) + "\\\\",
                         f"危险：测试正在操作真实用户目录 {resolved}")


if __name__ == "__main__":
    unittest.main()
