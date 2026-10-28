# This script contains the following functions:
#
# - un.DelAppPathSub and UnAppPreSuff,
#    (delete the folder ~\Documents and Settings\username\Application Data\FreeCAD for all users), uses:
#    un.GetParentA
#    un.GetUsers
#    un.StrPoint
#    StrPointer
#    StrPoint
#    UnAppPreSuff
#
# - FileCheck (checks if a given file exists)
#
#--------------------------

!macro StrPointer FindStr SearchStr Pointer
 # searches for a string/character (SearchStr) in another string (FindStr)
 # and returns the number of the character in the FindStr where the SearchStr was found (Pointer)
 # if nothing was found or the search is impossible the Pointer is set to -1

 StrLen $R2 "${SearchStr}"
 StrLen $R4 "${FindStr}"
 StrCpy $R5 0
 ${if} $R2 == 0
 ${orif} $R4 == 0
  Goto NotFound
 ${endif}
 IntCmp $R4 $R2 loopA NotFound
 loopA:
  StrCpy $R3 "${FindStr}" $R2 $R5
  StrCmp $R3 "${SearchStr}" Found
  IntOp $R5 $R5 + 1
  IntCmp $R4 $R5 loopA NotFound
  Goto loopA
 Found:
  StrCpy ${Pointer} $R5
  Goto done
 NotFound:
  StrCpy ${Pointer} "-1"
 done:

!macroend

#--------------------------------

Function StrPoint
 !insertmacro StrPointer $String $Search $Pointer
FunctionEnd

#--------------------------------

!macro RevStrPointer FindStr SearchStr Pointer
 # searches for a string/character (SearchStr) in another string (FindStr) in reverse order
 # and returns the number of the character in the FindStr where the SearchStr was found (Pointer)
 # if nothing was found or the search is impossible the Pointer is set to +1

 StrLen $R2 ${SearchStr}
 StrLen $R4 ${FindStr}
 ${if} $R2 == 0
 ${orif} $R4 == 0
  Goto NotFound
 ${endif}
 IntCmp $R4 $R2 loopA NotFound
 StrCpy $R5 "-$R2"
 loopA:
  StrCpy $R3 ${FindStr} $R2 $R5
  StrCmp $R3 ${SearchStr} Found
  IntOp $R5 $R5 - 1
  IntCmp "$R5" "-$R4" loopA NotFound
  Goto loopA
 Found:
  StrCpy ${Pointer} $R5
  Goto done
 NotFound:
  StrCpy ${Pointer} "+1"
 done:

!macroend

#--------------------------------

!macro AppPreSuff AppPre AppSuff
 # the APPDATA path for a local user has for WinXP and 2000 the following structure:
 # C:\Documents and Settings\username\Application Data
 # for Win Vista the structure is:
 # C:\Users\username\AppData\Roaming
 # this macro saves the "C:\Documents and Settings\" substring into the variable "AppPre"
 # and the "Application Data" substring into the variable "AppSuff"

  # switch temporarily to local user because the all users application data path is in
  # Vista only C:\ProgramData
  SetShellVarContext current
  StrCpy $String "$APPDATA"
  Var /GLOBAL APPDATemp
  StrCpy $APPDATemp "$APPDATA"
  ${If} $MultiUser.Privileges == "Admin"
   ${OrIf} $MultiUser.Privileges == "Power"
    SetShellVarContext all # move back to all users
  ${endif}
  StrCpy $Search "\"
  Call StrPoint # search for the first "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy $String $String "" $Pointer # cut off the part before the first "\"
  StrCpy $0 $Pointer
  Call StrPoint # search for the second "\"
  IntOp $0 $0 + $Pointer # $0 is now the pointer to the second "\" in the APPDATA string
  StrCpy ${AppPre} $APPDATemp $0 # save the part before the second "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy $String $String "" $Pointer # cut off the part before the second "\"
  Call StrPoint # search for the third "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy ${AppSuff} $String "" $Pointer # save the part after the third "\"

!macroend

#--------------------------------

Function un.GetParentA
 # deletes a subfolder of the APPDATA path for all users
 # used by the function "un.getUsers"

  Exch $R0
  Push $R1
  Push $R2
  Push $R3
  StrCpy $R1 0
  StrLen $R2 $R0
  loop:
   IntOp $R1 $R1 + 1
   IntCmp $R1 $R2 get 0 get
   StrCpy $R3 $R0 1 -$R1
   StrCmp $R3 "\" get
  Goto loop
  get:
   StrCpy $R0 $R0 -$R1
   Pop $R3
   Pop $R2
   Pop $R1
   Exch $R0

FunctionEnd

#--------------------------------

Function un.GetUsers
 # reads the subfolders of the "Documents and Settings" folder to get a list of the users

  StrCpy $R3 ""
  Push "$PROFILE"
  Call un.GetParentA
  Pop $R2
  StrCpy $R2 "$R2"
  FindFirst $R0 $R1 "$R2\*"
  StrCmp $R1 "" findend 0
  findloop:
   IfFileExists "$R2\$R1\*.*" 0 notDir
   StrCmp $R1 "." notDir
   StrCmp $R1 ".." notDir
   StrCmp $R1 "All Users" notDir
   StrCmp $R1 "Default User" notDir
   StrCmp $R1 "All Users.WINNT" notDir
   StrCmp $R1 "Default User.WINNT" notDir
  StrCpy $R3 "$R3|$R1"
  notDir:
   FindNext $R0 $R1
   StrCmp $R1 "" findend 0
  Goto findloop
  findend:
   FindClose $R0

FunctionEnd

#--------------------------------

Function un.StrPoint
 !insertmacro StrPointer $String $Search $Pointer
FunctionEnd

#--------------------------------

!macro UnAppPreSuff AppPre AppSuff
 # the APPDATA path for a local user has for WinXP and 2000 the following structure:
 # C:\Documents and Settings\username\Application Data
 # for Win Vista the structure is:
 # C:\Users\username\AppData\Roaming
 # this macro saves the "C:\Documents and Settings\" substring into the variable "AppPre"
 # and the "Application Data" substring into the variable "AppSuff"

  SetShellVarContext current # switch temoprarily to local user
  StrCpy $String "$APPDATA"
  StrCpy $APPDATemp "$APPDATA"
  ${if} $MultiUser.Privileges == "Admin"
  ${orif} $MultiUser.Privileges == "Power"
   SetShellVarContext all # move back to all users
  ${endif}
  StrCpy $Search "\"
  Call un.StrPoint # search for the first "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy $String $String "" $Pointer # cut off the part before the first "\"
  StrCpy $0 $Pointer
  Call un.StrPoint # search for the second "\"
  IntOp $0 $0 + $Pointer # $0 is now the pointer to the second "\" in the APPDATA string
  StrCpy ${AppPre} $APPDATemp $0 # save the part before the second "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy $String $String "" $Pointer # cut off the part before the second "\"
  Call un.StrPoint # search for the third "\"
  IntOp $Pointer $Pointer + 1 # jump after the "\"
  StrCpy ${AppSuff} $String "" $Pointer # save the part after the third "\"

!macroend

#--------------------------------

Function un.DelAppPathSub
 # deletes a subfolder of the APPDATA path for all users

  # get list of all users
  Push $R0
  Push $R1
  Push $R2
  Push $R3
  Call un.GetUsers
  StrCpy $UserList $R3 "" 1 # cut off the "|" at the end of the list
  Pop $R3
  Pop $R2
  Pop $R1
  Pop $R0

  # the usernames in the list of all users is separated by "|"
  loop:
   StrCpy $String "$UserList"
   StrCpy $Search "|"
   Call un.StrPoint # search for the "|"
   StrCmp $Pointer "-1" ready
   StrCpy $0 $UserList $Pointer # $0 contains now the username
   IntOp $Pointer $Pointer + 1 # jump after the "|"
   StrCpy $UserList $UserList "" $Pointer # cut off the first username in the list
   # generate the string for the current user
   # AppPre and AppSuff are generated in the macro "AppPreSuff"
   RMDir /r "$AppPre\$0\$AppSuff\$AppSubfolder" # delete the folder
  Goto loop
  ready:
  StrCpy $0 $UserList
  RMDir /r "$AppPre\$0\$AppSuff\$AppSubfolder" # delete the folder

FunctionEnd

#--------------------------------
#source: https://nsis.sourceforge.io/Trim_quotes

Function TrimQuotes
Exch $R0
Push $R1

  StrCpy $R1 $R0 1
  StrCmp $R1 `"` 0 +2
    StrCpy $R0 $R0 `` 1
  StrCpy $R1 $R0 1 -1
  StrCmp $R1 `"` 0 +2
    StrCpy $R0 $R0 -1

Pop $R1
Exch $R0
FunctionEnd

!macro _TrimQuotes Input Output
  Push `${Input}`
  Call TrimQuotes
  Pop ${Output}
!macroend
!define TrimQuotes `!insertmacro _TrimQuotes`

Function ValidateInstallDir
  # if the $INSTDIR does not contain "FreeCAD" we must add a subfolder to avoid that FreeCAD will e.g.
  # be installed directly to C:\programs - the uninstaller will then delete the whole
  # C:\programs directory
  StrCpy $String "$INSTDIR"
  StrCpy $Search "${APP_NAME}"
  Call StrPoint # function from Utils.nsh
  ${if} $Pointer == "-1"
    StrCpy $INSTDIR "$INSTDIR\${APP_DIR}"
  ${endif}
  # Make sure install dir is empty, avoids library conflicts from mixed installs
  Push $R0
  ${DirState} "$INSTDIR" $R0
  ${If} $R0 == 1
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "$(DirNotEmptyWarning)" /SD IDYES IDYES SetRemoveInstDir IDNO RejectDir

    SetRemoveInstDir:
      StrCpy $RemoveInstDir "true"
      Goto EndCheck

    RejectDir:
      Abort

    EndCheck:
  ${EndIf}
  Pop $R0
FunctionEnd

!macro _DetailPrintToBoth DETAIL_MESSAGE
  SetDetailsPrint both
  DetailPrint "${DETAIL_MESSAGE}"
  SetDetailsPrint lastused
!macroend
!define DetailPrintToBoth `!insertmacro _DetailPrintToBoth`

# based on https://nsis.sourceforge.io/Check_whether_your_application_is_running#Using_the_name_of_the_process_(with_Windows'_tasklist_command)
!macro _FindProc result processName
  nsExec::Exec '"$SYSDIR\cmd.exe" /c ""$SYSDIR\tasklist.exe" /NH /FI "IMAGENAME eq ${processName}" | "$SYSDIR\find.exe" /I "${processName}""'
  Pop ${result}
!macroend
!define FindProc `!insertmacro _FindProc`

# SCIFORGE: programs still running from the install folder, and replacing that folder without
# ever leaving half of it (docs/sciforge/core-patches.md #19). SciForge's AI connector is
# SciForge's own bin\python.exe: Claude Desktop (or Gemini CLI, Claude Code) starts it and keeps
# it running, SciForge closed or not. The check above only knows SciForge.exe and
# SciForgeCmd.exe, so an update deleted every file it could, stopped at the connector's open
# files ("Failed to remove") and left no working SciForge. Get-CimInstance gives the path of
# 64-bit processes from this 32-bit installer too.

# What runs from $INSTDIR: "" (nothing), "connector" (only python: the AI connector), or the
# programs' names ("SciForge.exe, python.exe").
!macro _SciForgeInFolder result
  ${DisableX64FSRedirection}
  nsExec::ExecToStack `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "try { $$d = '$INSTDIR\'; $$p = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$d, [StringComparison]::OrdinalIgnoreCase) }); if ($$p.Count -eq 0) { $$r = '' } elseif (@($$p | Where-Object { $$_.Name -notlike 'python*' }).Count -eq 0) { $$r = 'connector' } else { $$r = (@($$p | ForEach-Object { $$_.Name } | Sort-Object -Unique) -join ', ') }; [Console]::Out.Write($$r) } catch { }"`
  ${EnableX64FSRedirection}
  Pop ${result} # the exit code
  Pop ${result} # what it wrote
!macroend
!define SciForgeInFolder `!insertmacro _SciForgeInFolder`

# Stops the python processes started from $INSTDIR (the AI connector: harmless, the AI app
# starts it again the next time it opens).
!macro _SciForgeStopConnector
  Push $R9
  ${DisableX64FSRedirection}
  nsExec::ExecToStack `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$$d = '$INSTDIR\'; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $$_.Name -like 'python*' -and $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$d, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }"`
  ${EnableX64FSRedirection}
  Pop $R9
  Pop $R9
  Pop $R9
  Sleep 1000 # Windows lets go of the files a moment after
!macroend
!define SciForgeStopConnector `!insertmacro _SciForgeStopConnector`

# Leaves "ok" on the stack when no program runs from $INSTDIR any more (the connector is
# stopped after asking), "stop" when the person chose to stop: nothing was changed then.
!macro SCIFORGE_FOLDER_FREE UN
Function ${UN}SciForgeFolderFree
  Push $R0
  Push $R1
  StrCpy $R1 ""
  retry:
  ${SciForgeInFolder} $R0
  ${If} $R0 == "connector"
  ${AndIf} $R1 == ""
    MessageBox MB_OKCANCEL|MB_ICONINFORMATION "SciForge's AI connector is running: an AI app you connected to SciForge (Claude Desktop, Gemini CLI or Claude Code) keeps SciForge's python.exe open, so its files cannot be replaced.$\r$\n$\r$\nClick OK to stop the connector and go on (the AI app starts it again the next time it opens), or Cancel to stop here.$\r$\n$\r$\nNothing has been changed yet." /SD IDOK IDOK stopconnector
    StrCpy $R0 "stop"
    Goto done
    stopconnector:
    ${SciForgeStopConnector}
    StrCpy $R1 "tried"
    Goto retry
  ${ElseIf} $R0 != ""
    ${If} $R0 == "connector"
      StrCpy $R0 "python.exe (SciForge's AI connector: quit Claude Desktop from its icon by the clock, or close Gemini CLI or Claude Code)"
    ${EndIf}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Still running from '$INSTDIR': $R0.$\r$\n$\r$\nClose it (save your work first), then click Retry.$\r$\n$\r$\nNothing has been changed yet: the ${APP_NAME} you have still works." /SD IDCANCEL IDRETRY retry
    StrCpy $R0 "stop"
    Goto done
  ${EndIf}
  StrCpy $R0 "ok"
  done:
  Pop $R1
  Exch $R0
FunctionEnd
!macroend
!insertmacro SCIFORGE_FOLDER_FREE ""
!insertmacro SCIFORGE_FOLDER_FREE "un."

# Installing over an existing folder: once nothing runs from it, the old folder is moved aside
# in ONE step (Windows refuses while any file in it is open, and then nothing is lost) and only
# then deleted. Before, RMDir /r deleted file after file and gave up at the first one in use.
# Aborts the installation (nothing changed) when the person stops.
Function SciForgeReplaceInstDir
  Push $R0
  Push $R1
  SetOutPath "$TEMP" # (the installer's own working folder must not be inside the one it moves)
  retry:
  Call SciForgeFolderFree
  Pop $R0
  ${If} $R0 != "ok"
    Pop $R1
    Pop $R0
    Abort
  ${EndIf}
  StrCpy $R1 "$INSTDIR.old"
  ${If} ${FileExists} "$R1\*.*"
    RMDir /r "$R1" # what an earlier update could not delete
  ${EndIf}
  ${If} ${FileExists} "$R1\*.*"
    System::Call "kernel32::GetTickCount()i.R0"
    StrCpy $R1 "$INSTDIR.old-$R0"
  ${EndIf}
  ClearErrors
  Rename "$INSTDIR" "$R1"
  ${If} ${Errors}
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "A file in '$INSTDIR' is still open (an Explorer window or a command prompt in that folder, a program started from it, or a virus scan), so Windows does not let the old ${APP_NAME} be replaced.$\r$\n$\r$\nClose it, then click Retry.$\r$\n$\r$\nNothing has been changed yet: the ${APP_NAME} you have still works." /SD IDCANCEL IDRETRY retry
    Pop $R1
    Pop $R0
    Abort
  ${EndIf}
  ${DetailPrintToBoth} "Removing the old version (moved to '$R1')"
  ClearErrors
  RMDir /r "$R1"
  ${If} ${Errors}
    DetailPrint "Some files of the old version stay in '$R1' (in use); the next update removes them."
  ${EndIf}
  Pop $R1
  Pop $R0
FunctionEnd
