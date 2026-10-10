Option Explicit
Dim sh, fso, dir, pyFile, ts, pyExe, pyw, rc

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

pyw = ""
pyFile = dir & "\.python_path.txt"
If fso.FileExists(pyFile) Then
    Set ts = fso.OpenTextFile(pyFile, 1)
    pyExe = Trim(ts.ReadLine)
    ts.Close
    If fso.FileExists(pyExe) Then
        pyw = fso.GetParentFolderName(pyExe) & "\pythonw.exe"
        If Not fso.FileExists(pyw) Then pyw = ""
    End If
End If
If pyw = "" Then pyw = "pythonw"

' Estilo 1 (normal): pythonw no abre consola, y con estilo 0 Windows puede ocultar tambien la ventana del programa.
On Error Resume Next
rc = sh.Run("""" & pyw & """ """ & dir & "\app.py""", 1, True)
If Err.Number <> 0 Then rc = 1
On Error GoTo 0

If rc <> 0 Then
    MsgBox "No se pudo abrir osu! Recommender." & vbCrLf & vbCrLf & _
           "1) Ejecuta dependencies.bat" & vbCrLf & _
           "2) Si sigue fallando, revisa los archivos error.log y debug.log", 48, "osu! Recommender"
End If
