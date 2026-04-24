$ErrorActionPreference = 'Stop'

$pythonRoot = python -c "import sys; from pathlib import Path; print(Path(sys.executable).resolve().parent)"
$dllDir = Join-Path $pythonRoot 'DLLs'
$tclDir = Join-Path $pythonRoot 'tcl'
$tkinterLib = Join-Path $pythonRoot 'Lib\tkinter'
$tkinterPyd = Join-Path $dllDir '_tkinter.pyd'
$tclDll = Join-Path $dllDir 'tcl86t.dll'
$tkDll = Join-Path $dllDir 'tk86t.dll'
$env:TCL_LIBRARY = Join-Path $tclDir 'tcl8.6'
$env:TK_LIBRARY = Join-Path $tclDir 'tk8.6'

python -m PyInstaller `
  --clean `
  --onefile `
  --windowed `
  --runtime-hook "pyi_runtime_hook.py" `
  --hidden-import _tkinter `
  --collect-submodules tkinter `
  --add-binary "$tkinterPyd;." `
  --add-binary "$tclDll;." `
  --add-binary "$tkDll;." `
  --add-data "$tkinterLib;tkinter" `
  --add-data "$tclDir\tcl8.6;_tcl_data" `
  --add-data "$tclDir\tk8.6;_tk_data" `
  --name "ChaishuDesktop" `
  "chaishu_gui.py"

Write-Host "Build done: dist\ChaishuDesktop.exe"
