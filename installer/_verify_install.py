"""复核安装注册表与旧版本检测：有旧版→提示；无旧版→不提示。"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("D:/Deskface/软件开发")
TEST = ROOT / "installtest"


def reg_version():
    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TonyDash学习终端",
        )
        try:
            return winreg.QueryValueEx(key, "DisplayVersion")[0]
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return None


def main():
    print("=== 覆盖安装后 ===")
    print("registry DisplayVersion:", reg_version())
    print("installtest exe:", [p.name for p in TEST.glob("*.exe")])

    print("\n=== 卸载后（模拟全新安装）===")
    subprocess.run(["cmd", "/c", f"{TEST / 'Uninstall.exe'} /S"], check=False)
    time.sleep(2)
    print("registry DisplayVersion:", reg_version())
    print("installtest exe:", [p.name for p in TEST.glob("*.exe")])

    print("\n=== 无旧版本时再装新版（应无升级提示、静默完成）===")
    r = subprocess.run(
        ["cmd", "/c",
         f"{ROOT / 'release' / 'TonyDash学习终端-Beta1.5-Setup.exe'} /S "
         f"/D=D:\\Deskface\\软件开发\\installtest"],
        capture_output=True, text=True, check=False)
    time.sleep(4)
    print("exit:", r.returncode)
    print("installtest exe:", [p.name for p in TEST.glob("*.exe")])
    print("registry DisplayVersion:", reg_version())


main()
