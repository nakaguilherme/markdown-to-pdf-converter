"""
streamlit_md_to_pdf.py
=======================
App Streamlit que converte um arquivo Markdown (.md) em PDF.

Baseado no script `md_to_pdf.py` fornecido como referência: usa a mesma
lógica de renderização de diagramas Mermaid (```mermaid ... ```), o mesmo
CSS de formatação de tabelas/código, e o Chromium headless via Playwright
para gerar o PDF final (sem precisar de GTK/Pango/Cairo).

Adições em relação ao script original:
- Interface web (Streamlit) para upload do .md e dos assets (imagens)
  referenciados nele, com botão de download do PDF gerado.
- Suporte a fórmulas LaTeX (via MathJax, renderizado dentro do próprio
  Chromium antes de gerar o PDF).
- Suporte a tags HTML de estilização usadas dentro do Markdown, como
  <center>, <big>, <small>, <mark>, <sub>, <sup> etc. (via extensão
  `md_in_html` do python-markdown + CSS complementar, já que Chromium
  entende nativamente essas tags mesmo sendo "legadas").

DEPENDÊNCIAS
------------
    pip install streamlit markdown requests playwright
    playwright install chromium

Rodar com:
    streamlit run streamlit_md_to_pdf.py

RENDERIZAÇÃO DOS DIAGRAMAS MERMAID
-----------------------------------
Por padrão, o app usa o serviço público https://mermaid.ink (precisa de
internet). Se preferir renderizar localmente, instale o Mermaid CLI:
    npm install -g @mermaid-js/mermaid-cli
e marque a opção "Renderizar Mermaid localmente" na interface.
"""

import base64
import json
import re
import shutil
import subprocess
import tempfile
import zlib
from pathlib import Path

import markdown
import requests
import streamlit as st
from playwright.sync_api import sync_playwright

MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)

subprocess.run(
    ['playwright','install','chromium']
)
# --------------------------------------------------------------------------
# Renderização dos diagramas Mermaid (mesma lógica do script base)
# --------------------------------------------------------------------------

def render_mermaid_via_api(codigo: str, destino: Path) -> bool:
    """Renderiza um diagrama Mermaid usando o serviço mermaid.ink (requer internet)."""
    try:
        payload = {"code": codigo, "mermaid": {"theme": "default"}}
        comprimido = zlib.compress(json.dumps(payload).encode("utf-8"), 9)
        codificado = base64.urlsafe_b64encode(comprimido).decode("utf-8")
        url = f"https://mermaid.ink/img/pako:{codificado}?type=png&bgColor=white"

        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        destino.write_bytes(resp.content)
        return True
    except Exception as e:
        st.warning(f"Falha ao renderizar diagrama via mermaid.ink: {e}")
        return False


def render_mermaid_via_cli(codigo: str, destino: Path) -> bool:
    """Renderiza um diagrama Mermaid usando o mermaid-cli (mmdc) instalado localmente."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(codigo)
        caminho_entrada = tmp.name

    try:
        subprocess.run(
            ["mmdc", "-i", caminho_entrada, "-o", str(destino), "-b", "white", "-s", "2"],
            check=True,
            capture_output=True,
        )
        return True
    except FileNotFoundError:
        st.warning("'mmdc' não encontrado. Instale com: npm install -g @mermaid-js/mermaid-cli")
        return False
    except subprocess.CalledProcessError as e:
        st.warning(f"mmdc falhou: {e.stderr.decode(errors='ignore')}")
        return False
    finally:
        Path(caminho_entrada).unlink(missing_ok=True)


def substituir_diagramas_mermaid(md_texto: str, pasta_imagens: Path, usar_local: bool) -> str:
    """Encontra blocos ```mermaid```, renderiza cada um como PNG e troca o bloco
    pela sintaxe de imagem Markdown correspondente."""
    pasta_imagens.mkdir(parents=True, exist_ok=True)
    contador = 0

    def _substituir(match: re.Match) -> str:
        nonlocal contador
        contador += 1
        codigo = match.group(1).strip()
        destino = pasta_imagens / f"mermaid_{contador}.png"

        sucesso = (
            render_mermaid_via_cli(codigo, destino)
            if usar_local
            else render_mermaid_via_api(codigo, destino)
        )

        if sucesso and destino.exists():
            return f"\n![Diagrama Mermaid {contador}]({destino.as_posix()})\n"
        else:
            return f"\n```\n{codigo}\n```\n"

    return MERMAID_BLOCK_RE.sub(_substituir, md_texto)


# --------------------------------------------------------------------------
# CSS aplicado ao HTML antes de gerar o PDF
# --------------------------------------------------------------------------

CSS_TEMPLATE = """
body {
    font-family: "Helvetica Neue", Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.55;
    color: #222;
}

h1, h2, h3, h4, h5, h6 {
    color: #1a1a1a;
    font-weight: 700;
    margin-top: 1.4em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
}
h1 { font-size: 22pt; border-bottom: 2px solid #333; padding-bottom: 6px; }
h2 { font-size: 17pt; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
h3 { font-size: 14pt; }
h4 { font-size: 12pt; }

p { margin: 0.6em 0; orphans: 3; widows: 3; }

a { color: #0a5db0; text-decoration: none; }

code {
    font-family: "Consolas", "Menlo", monospace;
    background-color: #f2f2f2;
    padding: 2px 5px;
    border-radius: 3px;
    font-size: 0.9em;
}

pre {
    background-color: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 6px;
    padding: 12px;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; }

blockquote {
    border-left: 4px solid #ccc;
    margin: 0.8em 0;
    padding: 0.2em 1em;
    color: #555;
    background: #fafafa;
}

/* ---------- Tabelas ---------- */
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1.2em 0;
    font-size: 10pt;
    page-break-inside: avoid;
}
thead { display: table-header-group; }
tr { page-break-inside: avoid; }

th, td {
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}

th {
    background-color: #2d3e50;
    color: #ffffff;
    font-weight: 600;
}

tr:nth-child(even) td {
    background-color: #f5f7fa;
}

/* ---------- Imagens / diagramas Mermaid ---------- */
img {
    max-width: 100%;
    display: block;
    margin: 1em auto;
    page-break-inside: avoid;
}

ul, ol { margin: 0.5em 0; padding-left: 1.6em; }
li { margin: 0.25em 0; }

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.5em 0;
}

/* ---------- Tags HTML de estilização usadas dentro do Markdown ---------- */
center { display: block; text-align: center; }
big { font-size: 1.25em; }
small { font-size: 0.8em; }
mark { background-color: #fff3a3; padding: 0 2px; }
sub, sup { font-size: 0.75em; }
kbd {
    font-family: "Consolas", "Menlo", monospace;
    background-color: #f2f2f2;
    border: 1px solid #ccc;
    border-bottom-width: 2px;
    border-radius: 4px;
    padding: 1px 5px;
}

/* ---------- Fórmulas LaTeX renderizadas via MathJax ---------- */
mjx-container { page-break-inside: avoid; }
mjx-container[display="true"] { margin: 1em 0; }
"""

# Script do MathJax injetado no <head> do HTML para renderizar LaTeX
# (delimitadores $...$ e $$...$$, além de \(...\) e \[...\]).
MATHJAX_HEAD = """
<script>
window.MathJax = {
  tex: {
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
  },
  svg: { fontCache: 'global' }
};
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/3.2.2/es5/tex-mml-chtml.js"></script>
"""


# --------------------------------------------------------------------------
# Fluxo de conversão
# --------------------------------------------------------------------------

def converter_para_pdf(md_texto: str, pasta_trabalho: Path, usar_local_mermaid: bool) -> Path:
    """Recebe o texto do markdown e a pasta de trabalho (onde os assets/imagens
    enviados pelo usuário já foram salvos) e devolve o caminho do PDF gerado."""

    pasta_imagens = pasta_trabalho / "mermaid_assets"
    md_texto = substituir_diagramas_mermaid(md_texto, pasta_imagens, usar_local_mermaid)

    # `md_in_html` permite que Markdown seja processado dentro de tags HTML de
    # bloco (ex.: <center>...</center>), e o restante das tags inline
    # (<big>, <small>, <mark>, <sub>, <sup> etc.) já passam intactas pelo
    # python-markdown, sendo renderizadas nativamente pelo Chromium depois.
    html_corpo = markdown.markdown(
        md_texto,
        extensions=["extra", "tables", "fenced_code", "toc", "sane_lists", "md_in_html"],
    )

    html_completo = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>documento</title>
<style>{CSS_TEMPLATE}</style>
{MATHJAX_HEAD}
</head>
<body>
{html_corpo}
</body>
</html>"""

    # Salva o HTML na mesma pasta dos assets, para que caminhos relativos de
    # imagens (diagramas Mermaid e imagens enviadas pelo usuário) resolvam certo.
    html_tmp_path = pasta_trabalho / "documento_tmp.html"
    html_tmp_path.write_text(html_completo, encoding="utf-8")

    pdf_path = pasta_trabalho / "documento_saida.pdf"

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        pagina.goto(html_tmp_path.resolve().as_uri())
        pagina.wait_for_load_state("networkidle")

        # Aguarda o MathJax terminar de tipografar todas as fórmulas antes
        # de gerar o PDF (evita capturar o código LaTeX "cru" na página).
        try:
            pagina.evaluate(
                "async () => { if (window.MathJax && window.MathJax.startup) "
                "{ await window.MathJax.startup.promise; } }"
            )
        except Exception:
            pass

        pagina.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "2cm", "bottom": "2cm", "left": "1.8cm", "right": "1.8cm"},
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=(
                '<div style="width:100%; text-align:center; font-size:8px; color:#888;">'
                '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
            ),
        )
        navegador.close()

    return pdf_path


# --------------------------------------------------------------------------
# Interface Streamlit
# --------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Markdown → PDF", page_icon="📄", layout="centered")

    st.title("📄 Conversor de Markdown para PDF")
    st.write(
        "Envie um arquivo **.md** e receba de volta o mesmo documento em **PDF**, "
        "com suporte a diagramas Mermaid, tabelas, imagens, fórmulas em LaTeX "
        "(`$...$` e `$$...$$`) e tags HTML de estilização como `<center>`, "
        "`<big>` e `<small>`."
    )

    uploaded_md = st.file_uploader("Arquivo Markdown (.md)", type=["md", "markdown"])

    with st.expander("Assets/imagens referenciados no markdown (opcional)"):
        st.caption(
            "Se o seu .md referencia imagens locais (ex.: `![](foto.png)`), envie "
            "esses arquivos aqui para que sejam incluídos no PDF."
        )
        uploaded_assets = st.file_uploader(
            "Imagens",
            type=["png", "jpg", "jpeg", "gif", "svg", "webp"],
            accept_multiple_files=True,
        )

    usar_local_mermaid = st.checkbox(
        "Renderizar Mermaid localmente (mmdc)",
        value=False,
        help=(
            "Requer o mermaid-cli instalado (npm install -g @mermaid-js/mermaid-cli). "
            "Se desmarcado, os diagramas são renderizados pelo serviço público "
            "mermaid.ink (precisa de internet)."
        ),
    )

    nome_base = Path(uploaded_md.name).stem if uploaded_md else "documento"
    nome_saida = st.text_input("Nome do arquivo de saída", value=f"{nome_base}.pdf")

    converter_clicado = st.button(
        "Converter para PDF", type="primary", disabled=uploaded_md is None
    )

    if converter_clicado and uploaded_md is not None:
        with st.spinner("Convertendo... isso pode levar alguns segundos."):
            try:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    pasta_trabalho = Path(tmp_dir)

                    # Salva os assets enviados na pasta de trabalho, para que
                    # referências relativas de imagem no markdown funcionem.
                    if uploaded_assets:
                        for asset in uploaded_assets:
                            destino = pasta_trabalho / asset.name
                            destino.write_bytes(asset.getvalue())

                    md_texto = uploaded_md.getvalue().decode("utf-8")

                    pdf_path = converter_para_pdf(md_texto, pasta_trabalho, usar_local_mermaid)
                    pdf_bytes = pdf_path.read_bytes()

                st.success("PDF gerado com sucesso!")
                st.download_button(
                    "⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=nome_saida if nome_saida.endswith(".pdf") else f"{nome_saida}.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"Erro ao converter o arquivo: {e}")


if __name__ == "__main__":
    main()
