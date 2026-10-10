Option Explicit
Dim sh, fso, dir, vbsPath, desk, lnkPath, lnk, ico, wscriptExe

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
vbsPath = dir & "\o!br.vbs"

If Not fso.FileExists(vbsPath) Then
    MsgBox "No se encontro:" & vbCrLf & vbsPath & vbCrLf & vbCrLf & _
           "Deja este archivo en la misma carpeta que o!br.vbs.", 16, "osu! Recommender"
    WScript.Quit 1
End If

desk = sh.SpecialFolders("Desktop")
lnkPath = desk & "\osu! Recommender.lnk"
wscriptExe = sh.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\wscript.exe"

On Error Resume Next
Set lnk = sh.CreateShortcut(lnkPath)
lnk.TargetPath = wscriptExe
lnk.Arguments = """" & vbsPath & """"
lnk.WorkingDirectory = dir
lnk.Description = "osu! Beatmap Recommender"
ico = dir & "\assets\icon.ico"
If fso.FileExists(ico) Then lnk.IconLocation = ico & ",0"
lnk.Save
If Err.Number <> 0 Then
    MsgBox "No se pudo crear el acceso directo:" & vbCrLf & Err.Description & vbCrLf & vbCrLf & _
           "Destino: " & lnkPath, 16, "osu! Recommender"
    WScript.Quit 1
End If
On Error GoTo 0

If fso.FileExists(lnkPath) Then
    MsgBox "Acceso directo creado en:" & vbCrLf & lnkPath, 64, "osu! Recommender"
Else
    MsgBox "No se encontro el acceso directo despues de crearlo." & vbCrLf & lnkPath, 48, "osu! Recommender"
End If
