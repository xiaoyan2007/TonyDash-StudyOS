"""用 Python winreg 直接核验安装器写的注册表（reg.exe 对中文路径输出有编码问题）。"""
import winreg

BASE = winreg.HKEY_CURRENT_USER
UNINST = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
OLDKEY = "Software\\TonyDash学习终端"


def show(path):
    try:
        k = winreg.OpenKey(BASE, path)
    except FileNotFoundError:
        print(f"  [缺失] {path}")
        return
    n, _, _ = winreg.QueryInfoKey(k)
    vals = {}
    for i in range(n):
        vname = winreg.EnumValue(k, i)[0]
        vals[vname] = winreg.QueryValueEx(k, vname)[0]
    winreg.CloseKey(k)
    print(f"  [存在] {path}")
    for k2, v in vals.items():
        print(f"      {k2} = {v}")


print("=== 卸载信息 ===")
show(f"{UNINST}\\TonyDash学习终端")
print("=== 安装位置记录 ===")
show(OLDKEY)
print("=== 自启项 ===")
show("Software\\Microsoft\\Windows\\CurrentVersion\\Run")
print("=== WOW6432Node 视图 ===")
show(f"Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\TonyDash学习终端")
