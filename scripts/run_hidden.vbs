' Run 更新数据.bat silently (no console window).
' Used by Windows Task Scheduler.
Option Explicit

Dim fso, shell, root, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
bat = root & "\" & ChrW(&H66F4) & ChrW(&H65B0) & ChrW(&H6570) & ChrW(&H636E) & ".bat"
' ChrW codes above spell 更新数据 so this file itself stays pure ASCII.

If Not fso.FileExists(bat) Then
    WScript.Quit 1
End If

shell.Run """" & bat & """ /quiet", 0, False
