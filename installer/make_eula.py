"""Generate the EULA text and the RTF copy used by the NSIS license page."""
from pathlib import Path

TEXT = r"""TonyDash学习终端 用户协议

版本：Beta 1.4
更新日期：2026-11-04

感谢你使用 TonyDash学习终端（以下简称“本软件”）。本软件是一款面向本科生的本地学习辅助工具，提供课程表、期末考试、待办清单、学习概览与启动动画。请在使用前认真阅读本协议；点击“我同意”或继续安装，即表示你接受以下条款。

一、许可与使用
1. 本软件免费提供，供个人学习、教学演示等非商业用途使用。
2. 你可以将本软件安装在自己的电脑上，并可自行备份安装目录；但不得将本软件或其修改版用于出售、出租、捆绑推广等商业行为。
3. 未经作者书面许可，不得对本软件进行反向工程、反编译，或以本软件名义发布误导性修改版。

二、数据与隐私
1. 课程、考试、待办、设置等数据默认保存在本机 %APPDATA%\CampusPlanner\data.json，本软件不提供账号系统，也不会上传这些数据。
2. 软件不主动收集个人信息；导入、导出与日历文件均由你在本机操作。
3. 卸载或覆盖安装软件默认不会删除上述数据；如需彻底清理，请手动删除该数据目录。
4. 安装程序启动时会检测本机是否已安装旧版本：找不到旧版本时不显示任何升级提示；找到时会弹窗询问是否覆盖安装，你可以选择继续覆盖或取消。

三、备份与风险
1. 本软件按“现状”提供，作者会尽力修复问题，但不保证运行绝对不中断、数据绝对不丢失。
2. 在升级、重装或更换电脑前，请使用设置页的“导出备份 JSON”功能保存数据。
3. 因误操作、系统故障、杀毒软件拦截、磁盘损坏等造成的损失，作者不承担赔偿责任；请自行做好备份。

四、使用规范
1. 不得利用本软件从事违法违规活动，或传播侵害他人权益的内容。
2. 不得去除、隐藏本软件中的版权与作者标识，或以作者名义作出虚假承诺。
3. 鸣谢名单中列出的同学仅用于致谢，不代表其对软件内容或观点的认可。

五、更新与终止
1. 作者可能不定期发布更新版本；更新内容以应用内更新日志和发布说明为准。
2. 如你违反本协议，作者可停止提供更新或支持；已安装版本的使用风险由你自行承担。

六、其他
1. 本协议适用中华人民共和国法律。因本协议产生的争议，双方应友好协商解决。
2. 本协议未尽事宜，以软件发布页面和更新日志中的说明为准。
3. 如你不同意本协议，请取消安装并删除已下载的安装包。

安装并继续使用本软件，表示你已阅读、理解并同意本协议。
"""

BS = chr(92)


def esc(value: str) -> str:
    out = []
    for ch in value:
        code = ord(ch)
        if ch == BS:
            out.append(BS + BS)
        elif ch == "{":
            out.append(BS + "{")
        elif ch == "}":
            out.append(BS + "}")
        elif ch == "\n":
            out.append(BS + "par\n")
        elif ch == "\t":
            out.append(BS + "tab ")
        elif code < 128:
            out.append(ch)
        else:
            signed = code if code <= 32767 else code - 65536
            out.append(BS + f"u{signed}?")
    return "".join(out)


def build_rtf(text: str) -> str:
    body = []
    for line in text.splitlines():
        if not line.strip():
            body.append(BS + "par")
        elif line.startswith("TonyDash学习终端 用户协议"):
            body.append(BS + "pard" + BS + "qc" + BS + "b" + BS + "fs32 " + esc(line) + BS + "b0" + BS + "par")
        elif line.startswith("版本：") or line.startswith("更新日期："):
            body.append(BS + "pard" + BS + "qc" + BS + "fs18" + BS + "cf1 " + esc(line) + BS + "cf0" + BS + "par")
        elif line.startswith(("一、", "二、", "三、", "四、", "五、", "六、")):
            body.append(BS + "pard" + BS + "sa60" + BS + "sb120" + BS + "b" + BS + "fs22 " + esc(line) + BS + "b0" + BS + "par")
        elif line.startswith(("1.", "2.", "3.")):
            body.append(BS + "pard" + BS + "fi-180" + BS + "li360" + BS + "sa60" + BS + "fs20 " + esc(line) + BS + "par")
        elif line.startswith("安装并继续使用"):
            body.append(BS + "pard" + BS + "sa120" + BS + "sb180" + BS + "b" + BS + "fs20 " + esc(line) + BS + "b0" + BS + "par")
        else:
            body.append(BS + "pard" + BS + "sa80" + BS + "fs20 " + esc(line) + BS + "par")
    head = (
        "{" + BS + "rtf1" + BS + "ansi" + BS + "ansicpg936" + BS + "deff0"
        "{" + BS + "fonttbl{" + BS + "f0" + BS + "fnil" + BS + "fcharset134 Microsoft YaHei;}}"
        "{" + BS + "colortbl;" + BS + "red95" + BS + "green95" + BS + "blue102;}"
        + BS + "viewkind4" + BS + "uc1 "
    )
    return head + "".join(body) + "}"


def main() -> None:
    root = Path(__file__).resolve().parent
    (root / "EULA.txt").write_text(TEXT, encoding="utf-8-sig")
    (root / "EULA.rtf").write_text(build_rtf(TEXT), encoding="ascii")
    print("EULA.txt", (root / "EULA.txt").stat().st_size, "bytes")
    print("EULA.rtf", (root / "EULA.rtf").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
