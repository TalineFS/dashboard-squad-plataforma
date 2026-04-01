"""
Página Monte Carlo — integração com o dashboard Streamlit existente
===================================================================
Como usar no seu app principal:

    # app.py ou main.py
    import monte_carlo_page
    monte_carlo_page.render()

Ou com st.navigation / pages/:
    Salve este arquivo como pages/monte_carlo.py

Dependências (adicione ao requirements.txt):
    pandas
    matplotlib
    numpy
    streamlit
"""

import random
from collections import Counter
from datetime import datetime, timedelta
from io import StringIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

# ── Constantes ────────────────────────────────────────────────────────────────

N_SIMULACOES = 10_000
PERCENTIS = [50, 70, 85, 95]

POSSIVEIS_COLUNAS_RESOLUCAO = [
    "Resolved", "Resolution Date", "resolutiondate",
    "Resolved Date", "Date Resolved", "End Date",
]

COR_P = {50: "#3B6D11", 70: "#854F0B", 85: "#185FA5", 95: "#A32D2D"}
COR_HIST = "#85B7EB"
COR_GRID = "#E8E6DF"


# ── Helpers de dados ──────────────────────────────────────────────────────────

def _detectar_coluna_resolucao(df: pd.DataFrame) -> str | None:
    for col in POSSIVEIS_COLUNAS_RESOLUCAO:
        if col in df.columns:
            return col
    for col in df.columns:
        if any(k in col.lower() for k in ("resolv", "end date", "finish")):
            return col
    return None


@st.cache_data(show_spinner=False)
def carregar_csv(conteudo: bytes) -> pd.DataFrame:
    df = pd.read_csv(StringIO(conteudo.decode("utf-8-sig")), low_memory=False)
    df.columns = df.columns.str.strip()
    return df


def extrair_throughput(df: pd.DataFrame, col_res: str,
                       col_tipo: str | None, filtro_tipo: str | None,
                       historico_dias: int) -> dict:
    serie = pd.to_datetime(df[col_res], errors="coerce", dayfirst=True)
    if filtro_tipo and col_tipo:
        mascara = df[col_tipo].str.lower().str.strip() == filtro_tipo.lower()
        serie = serie[mascara]
    serie = serie.dropna()
    throughput = dict(Counter(serie.dt.date))
    if throughput:
        data_max = max(throughput.keys())
        corte = data_max - timedelta(days=historico_dias)
        throughput = {d: v for d, v in throughput.items() if d >= corte}
    return throughput


# ── Motor Monte Carlo ──────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def simular_how_many(amostras_tuple: tuple, horizonte: int) -> list:
    amostras = list(amostras_tuple)
    return sorted(
        [sum(random.choice(amostras) for _ in range(horizonte))
         for _ in range(N_SIMULACOES)],
        reverse=True,
    )


@st.cache_data(show_spinner=False)
def simular_when(amostras_tuple: tuple, n_features: int) -> list:
    amostras = list(amostras_tuple)
    resultados = []
    for _ in range(N_SIMULACOES):
        rem, dias = n_features, 0
        while rem > 0 and dias < 500:
            rem -= max(0, random.choice(amostras))
            dias += 1
        resultados.append(min(dias, 500))
    return sorted(resultados)


def calcular_percentis(resultados: list, modo: str) -> dict:
    arr = np.array(resultados)
    return {
        p: int(np.percentile(arr, 100 - p if modo == "howmany" else p))
        for p in PERCENTIS
    }


# ── Gráficos Matplotlib ───────────────────────────────────────────────────────

def _base_fig(w=10, h=3.8):
    fig, ax = plt.subplots(figsize=(w, h), facecolor="none")
    ax.set_facecolor("none")
    ax.tick_params(colors="#5F5E5A", labelsize=9)
    ax.yaxis.grid(True, color=COR_GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_color(COR_GRID)
    return fig, ax


def fig_throughput(throughput: dict) -> plt.Figure:
    datas = sorted(throughput.keys())
    vals = [throughput[d] for d in datas]
    media = np.mean(vals)
    fig, ax = _base_fig(h=3.2)
    ax.bar(datas, vals, color=COR_HIST, width=0.8, linewidth=0)
    ax.axhline(media, color=COR_P[85], linewidth=1.5, linestyle="--",
               label=f"Média: {media:.1f} cards/dia")
    ax.set_ylabel("Cards concluídos", fontsize=9, color="#5F5E5A")
    ax.legend(fontsize=8)
    plt.tight_layout(pad=1.2)
    return fig


def fig_distribuicao(resultados: list, pcts: dict, modo: str,
                     titulo_extra: str = "") -> plt.Figure:
    fig, ax = _base_fig(h=4.0)
    ax.hist(resultados, bins=60, color=COR_HIST, edgecolor="white",
            linewidth=0.2, density=True)
    for p, val in pcts.items():
        ax.axvline(val, color=COR_P[p], linewidth=2, linestyle="--")
        ax.text(val, ax.get_ylim()[1] * 0.03,
                f" {p}%\n {val}", color=COR_P[p], fontsize=8, va="bottom")
    xlabel = "Features entregues" if modo == "howmany" else "Dias úteis"
    ax.set_xlabel(xlabel, fontsize=9, color="#5F5E5A")
    ax.set_ylabel("Densidade", fontsize=9, color="#5F5E5A")
    if titulo_extra:
        ax.set_title(titulo_extra, fontsize=10, color="#444441",
                     fontweight="normal", pad=10)
    plt.tight_layout(pad=1.2)
    return fig


# ── UI ─────────────────────────────────────────────────────────────────────────

def _metricas_row(pcts: dict, modo: str, horizonte: int = None,
                  n_features: int = None, throughput: dict = None):
    media = round(np.mean(list(throughput.values())), 1) if throughput else 0
    cols = st.columns(5)
    with cols[0]:
        st.metric("Throughput médio", f"{media:.1f}", "cards/dia")
    rotulos = {50: "Otimista (50%)", 70: "Provável (70%)",
               85: "Recomendado (85%)", 95: "Seguro (95%)"}
    for i, p in enumerate(PERCENTIS):
        val = pcts[p]
        sufixo = " features" if modo == "howmany" else " dias úteis"
        with cols[i + 1]:
            st.metric(rotulos[p], f"{val}{sufixo}")


def _tabela_resultado(pcts: dict, modo: str, n_features: int = None):
    hoje = datetime.today()
    rows = []
    for p in PERCENTIS:
        val = pcts[p]
        if modo == "howmany":
            rows.append({"Confiança": f"{p}%", "Mínimo de features": val,
                         "Usar para": _uso(p)})
        else:
            data_est = hoje + timedelta(days=int(val * 1.4))
            rows.append({"Confiança": f"{p}%", "Dias úteis": val,
                         "Data estimada": data_est.strftime("%d/%m/%Y"),
                         "Usar para": _uso(p)})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _uso(p):
    return {
        50: "Estimativa interna / otimista",
        70: "Planejamento de squad",
        85: "Compromisso com PO/PM",
        95: "Stakeholders externos / contrato",
    }[p]


def render():
    st.title("Monte Carlo — Previsão de entrega")
    st.caption(
        "Baseado em dados históricos de throughput do Jira. "
        "Sem story points, sem estimativas — só dados reais de entrega."
    )

    # ── Upload ──────────────────────────────────────────────────────────────
    with st.expander("1. Carregar CSV do Jira", expanded=True):
        st.markdown(
            "Exporte no Jira: **Issues → Export → Export Excel CSV (all fields)**. "
            "Inclua os campos: Summary, Status, Issue Type, Created, Resolved."
        )
        arquivo = st.file_uploader("CSV exportado do Jira", type=["csv"],
                                   label_visibility="collapsed")

    if arquivo is None:
        st.info("Faça o upload do CSV do Jira para continuar.")
        _demo_inline()
        return

    df = carregar_csv(arquivo.read())

    col_res = _detectar_coluna_resolucao(df)
    if col_res is None:
        st.error(
            "Não foi possível detectar a coluna de data de resolução. "
            "Certifique-se de que o CSV contém 'Resolved' ou 'Resolution Date'."
        )
        st.write("Colunas encontradas:", list(df.columns))
        return

    col_tipo = next((c for c in ["Issue Type", "Issuetype", "Type"] if c in df.columns), None)
    tipos_disponiveis = sorted(df[col_tipo].dropna().unique().tolist()) if col_tipo else []

    # ── Configurações ────────────────────────────────────────────────────────
    with st.expander("2. Configurar simulação", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            modo = st.radio(
                "Pergunta a responder",
                options=["howmany", "when"],
                format_func=lambda x: {
                    "howmany": "How Many — quantas features em X dias?",
                    "when": "When — quando terminamos N features?",
                }[x],
                horizontal=False,
            )
        with c2:
            historico_dias = st.slider(
                "Janela histórica (dias)", 30, 180, 90, 10,
                help="Quantos dias de throughput passado usar como base"
            )
            filtro_tipo = None
            if tipos_disponiveis:
                opcoes = ["Todos"] + tipos_disponiveis
                sel = st.selectbox("Filtrar por Issue Type", opcoes)
                filtro_tipo = None if sel == "Todos" else sel

        if modo == "howmany":
            horizonte = st.slider("Horizonte (dias úteis)", 5, 90, 30, 5)
            n_features = None
        else:
            n_features = st.number_input("Features a entregar", 1, 500, 30, 5)
            horizonte = None

    # ── Throughput ───────────────────────────────────────────────────────────
    throughput = extrair_throughput(df, col_res, col_tipo, filtro_tipo, historico_dias)

    if not throughput:
        st.error(
            "Nenhum card com data de resolução encontrado no período. "
            "Verifique o CSV ou aumente a janela histórica."
        )
        return

    n_dias_dados = len(throughput)
    media_thr = np.mean(list(throughput.values()))

    st.markdown("---")
    c1, c2, c3 = st.columns(3)
    c1.metric("Dias com dados", n_dias_dados)
    c2.metric("Throughput médio", f"{media_thr:.1f} cards/dia")
    c3.metric("Total de cards concluídos", int(sum(throughput.values())))

    if n_dias_dados < 10:
        st.warning(
            "Histórico muito pequeno (< 10 dias com dados). "
            "Resultados podem não ser confiáveis — aumente a janela histórica."
        )

    with st.expander("Throughput histórico", expanded=False):
        st.pyplot(fig_throughput(throughput), use_container_width=True)

    # ── Simulação ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Resultado da simulação")

    amostras = tuple(throughput.values())
    with st.spinner(f"Rodando {N_SIMULACOES:,} simulações..."):
        if modo == "howmany":
            resultados = simular_how_many(amostras, horizonte)
            titulo_extra = f"{horizonte} dias úteis | throughput histórico: últimos {historico_dias} dias"
        else:
            resultados = simular_when(amostras, int(n_features))
            titulo_extra = f"{n_features} features | throughput histórico: últimos {historico_dias} dias"

    pcts = calcular_percentis(resultados, modo)

    _metricas_row(pcts, modo, horizonte, n_features, throughput)
    st.pyplot(
        fig_distribuicao(resultados, pcts, modo, titulo_extra),
        use_container_width=True,
    )
    _tabela_resultado(pcts, modo, n_features)

    # ── Interpretação ────────────────────────────────────────────────────────
    p85 = pcts[85]
    if modo == "howmany":
        st.info(
            f"**Recomendação:** com 85% de confiança, o squad entrega pelo menos "
            f"**{p85} features** em {horizonte} dias úteis. "
            "Use esse número para comprometer com o PO/PM."
        )
    else:
        data_est = (datetime.today() + timedelta(days=int(p85 * 1.4))).strftime("%d/%m/%Y")
        st.info(
            f"**Recomendação:** com 85% de confiança, as {int(n_features)} features "
            f"ficam prontas em até **{p85} dias úteis** (aprox. {data_est}). "
            "Use esse prazo para comprometer com stakeholders."
        )

    # ── Export ───────────────────────────────────────────────────────────────
    with st.expander("Exportar resultado"):
        rows = []
        for p in PERCENTIS:
            val = pcts[p]
            if modo == "howmany":
                rows.append({"Confiança": f"{p}%", "Mínimo features": val,
                             "Uso recomendado": _uso(p)})
            else:
                data_est = (datetime.today() + timedelta(days=int(val * 1.4))).strftime("%d/%m/%Y")
                rows.append({"Confiança": f"{p}%", "Dias úteis": val,
                             "Data estimada": data_est, "Uso recomendado": _uso(p)})
        df_exp = pd.DataFrame(rows)
        st.download_button(
            "Baixar resultado (CSV)",
            df_exp.to_csv(index=False).encode("utf-8"),
            file_name=f"monte_carlo_{modo}_{datetime.today().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )


# ── Demo sem dados reais ───────────────────────────────────────────────────────

def _demo_inline():
    st.markdown("---")
    st.markdown("#### Prévia — dados de exemplo")
    st.caption("Assim ficará o resultado com seu CSV do Jira.")

    random.seed(99)
    thr_demo = {i: random.randint(0, 5) for i in range(60)}
    amostras = tuple(thr_demo.values())
    res = simular_how_many(amostras, 20)
    pcts = calcular_percentis(res, "howmany")

    _metricas_row(pcts, "howmany", horizonte=20, throughput=thr_demo)
    st.pyplot(
        fig_distribuicao(res, pcts, "howmany", "exemplo — 20 dias úteis"),
        use_container_width=True,
    )
    _tabela_resultado(pcts, "howmany")


# ── Entrypoint standalone ─────────────────────────────────────────────────────

if __name__ == "__main__":
    st.set_page_config(
        page_title="Monte Carlo | TF Serviços & Payments",
        page_icon="🎲",
        layout="wide",
    )
    render()
