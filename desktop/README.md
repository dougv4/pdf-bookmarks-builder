# Desktop App

Workspace do app desktop local com `Tauri + Python`.

## Objetivo do Release 1
- um PDF por vez
- sumario estruturado manual
- otimizacao opcional
- bookmarks + linearizacao
- processamento 100% local

## Rodar em desenvolvimento

Requisitos:
- Node.js
- Rust/Cargo
- Python 3
- `gs`
- `qpdf`

Frontend + shell desktop:

```bash
cd desktop
npm install
npm run tauri:dev
```

## Backend Python em dev

No modo de desenvolvimento, o shell desktop chama:

```bash
python3 desktop/backend_entrypoint.py <comando>
```

## Empacotamento

### Backend Python sidecar

```bash
cd desktop
./scripts/build_backend_sidecar.sh macos-arm64
```

Windows:

```powershell
cd desktop
.\scripts\build_backend_sidecar.ps1 -PlatformDir windows-x64
```

### Binaries nativos

```bash
cd desktop
./scripts/stage_macos_resources.sh macos-arm64
```

Isso prepara `resources/binaries/macos-arm64/` para o build do app.

Windows:

```powershell
cd desktop
.\scripts\stage_windows_resources.ps1 -PlatformDir windows-x64
```

## Build local dos instaladores

macOS:

```bash
cd desktop
./scripts/build_desktop_macos.sh macos-arm64
```

Windows:

```powershell
cd desktop
.\scripts\build_desktop_windows.ps1 -PlatformDir windows-x64
```

Saidas esperadas:
- `src-tauri/target/release/bundle/dmg/*.dmg`
- `src-tauri/target/release/bundle/msi/*.msi`
- `src-tauri/target/release/bundle/nsis/*.exe` (quando o target NSIS estiver habilitado)

## CI

Workflow:
- `.github/workflows/build-desktop.yml`

Jobs:
- `macos-14` -> `DMG`
- `windows-latest` -> `MSI`

## Observacao sobre Windows

O `MSI` nao pode ser gerado no macOS. O caminho suportado e:

- build em uma maquina Windows
- ou build no GitHub Actions (`windows-latest`)

O script `stage_windows_resources.ps1` empacota:
- `pdf-bookmarks-backend.exe`
- `gs.exe`
- `qpdf.exe`
- DLLs necessarias de Ghostscript/qpdf
- recursos do Ghostscript (`Resource`, `lib`, `fonts`, `iccprofiles`)

## Smoke test

Antes do build do instalador, a pipeline roda um smoke test real do backend:

```bash
python3 desktop/scripts/smoke_test_backend.py
```

## Licenciamento

Distribuir o app com `Ghostscript` embutido requer revisao do licenciamento do Ghostscript antes da publicacao externa.
