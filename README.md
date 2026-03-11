# PDF Bookmarks Builder

Aplicacao Streamlit para:
- subir um PDF
- otimizar tamanho com Ghostscript + qpdf
- colar um sumario estruturado
- gerar bookmarks/marcadores no PDF
- baixar o PDF final linearizado

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

## Otimizacao

O app pode otimizar o PDF antes de aplicar os bookmarks.

Parametros disponiveis na UI:
- `Color DPI`
- `Gray DPI`
- `JPEG quality`

Pipeline:
1. compressao com Ghostscript
2. linearizacao com qpdf
3. aplicacao dos bookmarks
4. linearizacao final

## Deploy no Streamlit Community Cloud

1. Suba este diretorio para um repositorio publico.
2. No Streamlit Cloud, use:
   - Branch: `main`
   - Main file path: `streamlit_app.py`
3. O arquivo `packages.txt` instala `ghostscript` e `qpdf`.
