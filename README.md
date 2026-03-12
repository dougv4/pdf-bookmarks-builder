# PDF Bookmarks Builder

Aplicacao Streamlit para:
- subir um PDF
- otimizar tamanho com Ghostscript + qpdf
- colar um sumario estruturado
- gerar bookmarks/marcadores no PDF
- baixar o PDF final linearizado

Agora o projeto possui duas apps:
- `streamlit_app.py`: V1 manual, com um PDF por vez
- `streamlit_batch_app.py`: V2 automatica, com varios PDFs por lote + OpenAI/Gemini
- `desktop/`: workspace do app desktop local com `Tauri + Python`

## Formato do sumario

Use uma linha por marcador:

```text
LEVEL | TITLE | PAGE
```

Niveis permitidos:
- `UNIT`
- `CHAPTER`
- `SECTION`

Exemplo:

```text
UNIT | UNIDADE 1: Olhares em perspectiva | 16
CHAPTER | CAPITULO 1: Romantismo: poesia (I) / Classes de palavras: revisao (I) / Noticia e enquete | 19
SECTION | LITERATURA | 19
SECTION | Foco no texto | 21
```

## Rodar localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Para a V2:

```bash
streamlit run streamlit_batch_app.py
```

## Desktop local

O workspace `desktop/` implementa a migracao do fluxo manual da V1 para um app desktop local.

Release 1 do desktop:
- um PDF por vez
- sumario estruturado manual
- otimizacao opcional
- bookmarks + linearizacao
- processamento local, sem Streamlit

Backend local:
- `python3 desktop/backend_entrypoint.py validate-preview`
- `python3 desktop/backend_entrypoint.py process-pdf`

O backend Python agora expoe um contrato reutilizavel para:
- validar preview
- processar o PDF final

Documentacao especifica:
- [`desktop/README.md`](desktop/README.md)

## Instaladores

O projeto agora inclui a base para gerar instaladores desktop:
- macOS: `DMG`
- Windows: `MSI`

No macOS, para distribuicao real, o pipeline precisa:
- assinar o bundle com `Developer ID Application`
- assinar os binarios internos (`backend`, `gs`, `qpdf`, `.dylib`)
- notarizar o artefato final

Sem isso, o Gatekeeper tende a marcar o app como danificado ou nao confiavel.

Arquivos principais:
- workflow CI: [`.github/workflows/build-desktop.yml`](.github/workflows/build-desktop.yml)
- scripts de build/staging: `desktop/scripts/`

Os binarios nativos do app continuam sendo:
- backend Python sidecar
- `Ghostscript`
- `qpdf`

## Licenciamento do Ghostscript

Ao distribuir instaladores com `Ghostscript` embutido, voce precisa revisar o licenciamento do Ghostscript (AGPL/comercial) antes de publicar para usuarios finais.

Referencias oficiais:
- [Ghostscript licensing](https://ghostscript.com/licensing/)
- [qpdf licensing](https://qpdf.readthedocs.io/en/stable/license.html)

## Otimizacao

As duas apps podem otimizar o PDF antes de aplicar os bookmarks.

Parametros disponiveis na UI:
- `Color DPI`
- `Gray DPI`
- `JPEG quality`

Pipeline:
1. compressao com Ghostscript
2. linearizacao com qpdf
3. aplicacao dos bookmarks
4. linearizacao final

## V2 automatica

Fluxo da V2:
1. upload de varios PDFs
2. leitura das paginas iniciais do PDF
3. deteccao automatica do bloco mais provavel de sumario
4. envio do bloco bruto para OpenAI ou Gemini
5. validacao da resposta no formato `LEVEL | TITLE | PAGE`
6. revisao manual por arquivo
7. geracao do lote final em ZIP

Conteudo do ZIP:
- PDFs finais processados
- `manifest.json`
- `summary.csv`
- `toc-preview.txt` e dumps de sumario por arquivo

Chaves de API:
- a API key fica apenas na sessao do Streamlit
- nao e salva em arquivo nem no repositrio

## Deploy no Streamlit Community Cloud

1. Suba este diretorio para um repositorio publico.
2. No Streamlit Cloud, use:
   - Branch: `main`
   - Main file path da V1: `streamlit_app.py`
   - Main file path da V2: `streamlit_batch_app.py`
3. O arquivo `packages.txt` instala `ghostscript` e `qpdf`.
