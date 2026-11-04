"""核验：这个环境里 HKCU 注册表写入是否真的能落盘（排除沙箱/重定向干扰）。"""
import winreg

BASE = winreg.HKEY_CURRENT_USER
TEST = "Software\\DSH_RegProbe"

print("=== 1) Python 写一个测试键 ===")
try:
    k = winreg.CreateKey(BASE, TEST)
    winreg.SetValueEx(k, "probe", 0, winreg.REG_SZ, "written-ok")
    winreg.CloseKey(k)
    print("  写入成功")
except OSError as e:
    print("  写入失败:", e)

print("=== 2) 读回 ===")
try:
    k = winreg.OpenKey(BASE, TEST)
    print("  probe =", winreg.QueryValueEx(k, "probe")[0])
    winreg.CloseKey(k)
except FileNotFoundError:
    print("  读不到（键不存在）")

print("=== 3) 卸载信息根键下的子键 ===")
try:
    k = winreg.OpenKey(BASE, "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall")
    n, _, _ = winreg.QueryInfoKey(k)
    names = [winreg.EnumKey(k, i) for i in range(n)]
    winreg.CloseKey(k)
    print("  子键数:", n)
    for x in names:
        print("   -", x)
except FileNotFoundError:
    print("  根键不存在")

print("=== 4) 清理测试键 ===")
try:
    winreg.DeleteKey(BASE, TEST)
    print("  已删除")
except OSError as e:
    print("  删除失败:", e)
