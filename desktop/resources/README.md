# Desktop resources

Este diretorio recebe artefatos empacotados para o app desktop.

Estrutura esperada no build:
- `resources/binaries/macos-arm64/pdf-bookmarks-backend`
- `resources/binaries/macos-arm64/gs`
- `resources/binaries/macos-arm64/qpdf`
- `resources/ghostscript/macos-arm64/Resource/`
- `resources/binaries/windows-x64/pdf-bookmarks-backend.exe`
- `resources/binaries/windows-x64/gs.exe`
- `resources/binaries/windows-x64/qpdf.exe`
- `resources/ghostscript/windows-x64/`

No modo de desenvolvimento, o app usa:
- `python3 desktop/backend_entrypoint.py`
- `gs` e `qpdf` do sistema

No modo empacotado, o runtime tenta primeiro os binarios embarcados em `resources/binaries/<platform>/`.

O diretorio `resources/ghostscript/<platform>/` contem os recursos complementares do Ghostscript (`Resource`, `lib`, `fonts`) usados no runtime.
