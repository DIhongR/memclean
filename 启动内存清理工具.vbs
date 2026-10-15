' ============================================================
'  Memory Cleaner - silent launcher (no black console window)
'  Double-click this file to run the tool in the system tray.
'  NOTE: keep this file ASCII-only; Windows Script Host reads
'        .vbs files using the ANSI code page.
' ============================================================
Option Explicit
Dim fso, sh, base, py, cmd, candidates, i

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)

' Try common pythonw.exe locations first, then fall back to PATH.
candidates = Array( _
    "D:\py\pythonw.exe", _
    "D:\py\Scripts\pythonw.exe", _
    "D:\Python\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python39\pythonw.exe", _
    "C:\Python313\pythonw.exe", _
    "C:\Python312\pythonw.exe", _
    "C:\Python311\pythonw.exe", _
    "C:\Python310\pythonw.exe" _
)

py = ""
For i = 0 To UBound(candidates)
    If fso.FileExists(candidates(i)) Then
        py = candidates(i)
        Exit For
    End If
Next
If py = "" Then py = "pythonw.exe"

If Not fso.FileExists(base & "\memclean.py") Then
    MsgBox "memclean.py was not found next to this launcher." & vbCrLf & _
           "Please keep both files in the same folder.", 16, "Memory Cleaner"
    WScript.Quit 1
End If

sh.CurrentDirectory = base
cmd = """" & py & """ """ & base & "\memclean.py"""
' 0 = hidden window, False = do not wait for the program to exit
sh.Run cmd, 0, False
