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
