"""诊断：注册表写入是否成功 + 确认框截图内容分析。"""
import subprocess
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path("D:/Deskface/软件开发")
TEST = ROOT / "installtest"
SHOTS = TEST / "_shots"


def reg_dump():
    import winreg

    base = winreg.HKEY_CURRENT_USER
    path = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
    try:
        key = winreg.OpenKey(base, path)
    except FileNotFoundError:
        print("  Uninstall 根键不存在")
        return
    n, _, _ = winreg.QueryInfoKey(key)
    for i in range(n):
        name = winreg.EnumKey(key, i)
        if "TonyDash" in name or "Campus" in name:
            try:
                k = winreg.OpenKey(base, f"{path}\\{name}")
                vals = {}
                for j in range(winreg.QueryInfoKey(k)[1]):
                    vname = winreg.EnumValue(k, j)[0]
                    vals[vname] = winreg.QueryValueEx(k, vname)[0]
                winreg.CloseKey(k)
                print("  找到:", name, vals)
            except FileNotFoundError:
                print("  找到(无值):", name)
    winreg.CloseKey(key)

    print("  HKCU64 旧键:")
    try:
        k = winreg.OpenKey(base, "Software\\TonyDash学习终端")
        vals = {}
        for i in range(winreg.QueryInfoKey(k)[1]):
            vname = winreg.EnumValue(k, i)[0]
            vals[vname] = winreg.QueryValueEx(k, vname)[0]
        winreg.CloseKey(k)
        print("   ", vals)
    except FileNotFoundError:
        print("    Software\\TonyDash学习终端 不存在")


def analyze(path):
    im = Image.open(path).convert("RGB")
    cnt = Counter(im.getdata())
    top = [(f"#{r:02X}{g:02X}{b:02X}", n) for (r, g, b), n in cnt.most_common(5)]
    print(f"  {path.name}: {im.size} top={top[:3]}")


print("=== 注册表现状 ===")
reg_dump()

print("\n=== 截图内容分析 ===")
for p in sorted(SHOTS.glob("*.png")):
    analyze(p)

print("\n=== 运行中的进程 ===")
subprocess.run(["tasklist", "/FI", "IMAGENAME eq TonyDash*.exe", "/FO", "CSV", "/NH"],
               check=False)
