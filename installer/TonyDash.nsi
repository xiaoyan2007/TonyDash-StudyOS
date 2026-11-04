; TonyDash学习终端 Beta 1.5 installer (NSIS 3 / Unicode)
Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "Sections.nsh"

!define APP_NAME "TonyDash学习终端"
!define APP_VERSION "Beta 1.5"
!define APP_EXE "TonyDash学习终端-Beta1.5.exe"
!define APP_SRC "..\release\TonyDash学习终端-Beta1.5"
!define APP_ICON "..\assets\app.ico"
!define APP_README "..\README.md"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\TonyDash学习终端"
!define OLD_KEY "Software\TonyDash学习终端"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\release\TonyDash学习终端-Beta1.5-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\TonyDash学习终端"
InstallDirRegKey HKCU "${OLD_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ShowInstDetails show
ShowUninstDetails show
BrandingText "${APP_NAME} · ${APP_VERSION}"
VIProductVersion "1.5.0.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "ProductVersion" "1.5.0.0"
VIAddVersionKey "CompanyName" "xiaoyan2007"
VIAddVersionKey "FileDescription" "${APP_NAME} 安装程序"
VIAddVersionKey "FileVersion" "1.5.0.0"
VIAddVersionKey "LegalCopyright" "© 2026 xiaoyan2007"

!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 ${APP_NAME}"
!define MUI_WELCOMEPAGE_TEXT "本向导将把 ${APP_NAME} ${APP_VERSION} 安装到你的电脑。$\r$\n$\r$\n安装包已内置 Python、Qt 与运行库，目标电脑不需要另外安装 Python 或开发环境。$\r$\n$\r$\n点击“下一步”继续。"
!define MUI_LICENSEPAGE_TEXT_TOP "请阅读以下用户协议。继续安装表示你接受协议内容。"
!define MUI_COMPONENTSPAGE_TEXT_TOP "请选择要创建的快捷方式与启动选项。"
!define MUI_DIRECTORYPAGE_TEXT_TOP "请选择 ${APP_NAME} 的安装位置。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "运行 ${APP_NAME}"
!define MUI_FINISHPAGE_LINK "查看项目主页"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/xiaoyan2007"

!insertmacro MUI_PAGE_WELCOME
Page custom fn_UpgradePage fn_UpgradeLeave
!insertmacro MUI_PAGE_LICENSE "EULA.rtf"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  SetShellVarContext current
  ; ---- 旧版本检测：$R9 保存检测到的旧版本号，空字符串表示没找到 ----
  ; 先查 64 位视图（应用是 64 位打包），再查 32 位视图，最后退回默认安装目录
  ReadRegStr $R9 HKCU64 "${UNINST_KEY}" "DisplayVersion"
  StrCmp $R9 "" try32
  StrCmp $R9 "0" try32
  Goto oldfound
  try32:
    ReadRegStr $R8 HKCU32 "${UNINST_KEY}" "DisplayVersion"
    StrCmp $R8 "" tryfile
    StrCmp $R8 "0" tryfile
    StrCpy $R9 $R8
    Goto oldfound
  tryfile:
    ${If} ${FileExists} "$LOCALAPPDATA\Programs\${APP_NAME}\Uninstall.exe"
      StrCpy $R9 "未知版本"
    ${Else}
      StrCpy $R9 ""
    ${EndIf}
  oldfound:
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

Function fn_UpgradePage
  ; 找不到旧版本时本页为空，等于把升级提示藏起来
  StrCmp $R9 "" done
  MessageBox MB_YESNO "检测到本机已安装旧版本 ${APP_NAME} $R9。是否覆盖安装？覆盖会替换旧版本程序；你的课表、考试与待办数据保存在 %APPDATA%\CampusPlanner，不会被删除。" /SD idYES
  Pop $0
  StrCmp $0 "Yes" done quit
  quit:
  Quit
  done:
FunctionEnd

Function fn_UpgradeLeave
FunctionEnd

Section "TonyDash学习终端（必需）" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  ; 覆盖安装：先清理旧版本的可执行文件与 _internal，
  ; 否则 File /r 只会覆盖同名文件，旧版 exe 会一直留在目录里。
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\TonyDash学习终端-Beta1.0.exe"
  Delete "$INSTDIR\TonyDash学习终端-Beta1.1.exe"
  Delete "$INSTDIR\TonyDash学习终端-Beta1.2.exe"
  Delete "$INSTDIR\TonyDash学习终端-Beta1.3.exe"
  Delete "$INSTDIR\TonyDash学习终端-Beta1.4.exe"
  File /r /x debug.log "${APP_SRC}\*.*"
  File /oname=用户协议.txt "EULA.txt"
  File /oname=README.md "${APP_README}"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\TonyDash学习终端"
  CreateShortCut "$SMPROGRAMS\TonyDash学习终端\TonyDash学习终端.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortCut "$SMPROGRAMS\TonyDash学习终端\卸载 TonyDash学习终端.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\TonyDash学习终端.lnk" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU64 "Software\Microsoft\Windows\CurrentVersion\Run" "TonyDash学习终端" '"$INSTDIR\${APP_EXE}"'

  WriteRegStr HKCU64 "${OLD_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU64 "${UNINST_KEY}" "DisplayName" "${APP_NAME} ${APP_VERSION}"
  WriteRegStr HKCU64 "${UNINST_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU64 "${UNINST_KEY}" "Publisher" "xiaoyan2007"
  WriteRegStr HKCU64 "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU64 "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU64 "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU64 "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "创建桌面快捷方式" SecDesktop
  CreateShortCut "$DESKTOP\TonyDash学习终端.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "开机自动启动（推荐）" SecStartup
  WriteRegStr HKCU64 "Software\Microsoft\Windows\CurrentVersion\Run" "TonyDash学习终端" '"$INSTDIR\${APP_EXE}"'
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "安装 TonyDash学习终端及运行所需组件（约 46 MB）。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "在桌面创建 TonyDash学习终端快捷方式。"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} "登录 Windows 时自动启动 TonyDash学习终端，默认开启。"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInstSuccess
  IfSilent done
  ; 升级时如果用户取消勾选，清理旧的快捷方式与自启项
  ${IfNot} ${SectionIsSelected} ${SecDesktop}
    Delete "$DESKTOP\TonyDash学习终端.lnk"
  ${EndIf}
  ${IfNot} ${SectionIsSelected} ${SecStartup}
    DeleteRegValue HKCU64 "Software\Microsoft\Windows\CurrentVersion\Run" "TonyDash学习终端"
  ${EndIf}
  done:
FunctionEnd

Section "Uninstall"
  Delete "$DESKTOP\TonyDash学习终端.lnk"
  Delete "$SMPROGRAMS\TonyDash学习终端\TonyDash学习终端.lnk"
  Delete "$SMPROGRAMS\TonyDash学习终端\卸载 TonyDash学习终端.lnk"
  RMDir "$SMPROGRAMS\TonyDash学习终端"
  DeleteRegValue HKCU64 "Software\Microsoft\Windows\CurrentVersion\Run" "TonyDash学习终端"
  DeleteRegKey HKCU64 "${UNINST_KEY}"
  DeleteRegKey HKCU64 "${OLD_KEY}"
  RMDir /r "$INSTDIR"
SectionEnd
