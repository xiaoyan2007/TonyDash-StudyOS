"""覆盖安装测试：截图留证 + 校验安装结果。"""
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/Deskface/软件开发")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "installtest" / "_shots"
OUT.mkdir(parents=True, exist_ok=True)


def shot(name):
    img = ImageGrab.grab()
    path = OUT / name
    img.save(str(path))
    print("shot", name, img.size, path)


def run_old():
    exe = ROOT / "installtest" / "TonyDash学习终端-Beta1.3.exe"
    env = dict(os.environ)
    env["APPDATA"] = str(ROOT / "installtest" / "_appdata_old")
    subprocess.Popen([str(exe)], env=env, cwd=str(ROOT / "installtest"))


def run_new():
    exe = ROOT / "installtest" / "TonyDash学习终端-Beta1.4.exe"
    env = dict(os.environ)
    env["APPDATA"] = str(ROOT / "installtest" / "_appdata_new")
    subprocess.Popen([str(exe)], env=env, cwd=str(ROOT / "installtest"))


def main():
    mode = sys.argv[3] if len(sys.argv) > 3 else ""
    if mode == "old":
        subprocess.Popen(["explorer.exe", str(ROOT / "installtest")])
        time.sleep(2.5)
        shot("01_old_folder.png")
        run_old()
        time.sleep(4.0)
        shot("02_old_running.png")
        print("DONE old")
    elif mode == "new":
        subprocess.Popen(["explorer.exe", str(ROOT / "installtest")])
        time.sleep(2.5)
        shot("03_new_folder.png")
        run_new()
        time.sleep(4.0)
        shot("04_new_running.png")
        print("DONE new")
    elif mode == "dialog":
        # 交互式运行新版安装包，截取旧版本检测确认框
        exe = ROOT / "release" / "TonyDash学习终端-Beta1.4-Setup.exe"
        subprocess.Popen([str(exe), "/D=D:\\Deskface\\软件开发\\installtest"],
                         cwd=str(ROOT / "installer"))
        time.sleep(6.0)
        shot("05_upgrade_confirm.png")
        print("DONE dialog")


main()
