import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from collections import defaultdict
import numpy as np

# ─── CONFIG ───
st.set_page_config(
    page_title="Dashboard Kanban — Squad Plataforma | TFSports",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── SECRETS ───
JIRA_URL = "https://trackfield.atlassian.net"
JIRA_EMAIL = st.secrets["jira"]["email"]
JIRA_TOKEN = st.secrets["jira"]["api_token"]
PROJECT_KEY = "SPT"

# ─── TEAM CONFIG ───
TEAM = {
    "hgp": {"name": "Guedes", "role": "Backend Dev", "color": "#f59e0b"},
    "gfm": {"name": "Guilherme", "role": "FullStack Dev", "color": "#6366f1"},
    "Leonardo Almeida": {"name": "Leonardo", "role": "QA Automação", "color": "#10b981"},
    "Marcelo Martins Oliveira": {"name": "Marcelo", "role": "Eng. Backend", "color": "#ef4444"},
    "ats": {"name": "Sato", "role": "Eng. Mobile", "color": "#ec4899"},
    "Ricardo Moro": {"name": "Ricardo", "role": "Ger. Arquitetura", "color": "#8b5cf6"},
}

STATUS_ORDER = ["Backlog", "To Do", "In Progress", "Code Review", "Validação", "Bloqueado", "BUGS", "Done"]
STATUS_COLORS = {
    "Backlog": "#94a3b8",
    "To Do": "#60a5fa",
    "In Progress": "#f59e0b",
    "Code Review": "#a78bfa",
    "Validação": "#38bdf8",
    "Bloqueado": "#ef4444",
    "BUGS": "#f87171",
    "Done": "#10b981",
}

TYPE_COLORS = {
    "Epic": "#8b5cf6",
    "Story": "#3b82f6",
    "Subtask": "#64748b",
    "Bug": "#ef4444",
    "Task": "#f59e0b",
}


# ─── JIRA API ───
@st.cache_data(ttl=300)
def fetch_jira_issues():
    """Busca todas as issues do projeto SPT via Jira API (endpoint /search/jql)."""
    all_issues = []
    next_page_token = None

    while True:
        url = f"{JIRA_URL}/rest/api/3/search/jql"
        payload = {
            "jql": f"project = {PROJECT_KEY} ORDER BY created DESC",
            "maxResults": 100,
            "fields": [
                "summary", "status", "issuetype", "priority", "assignee",
                "created", "resolutiondate", "updated", "resolution", "labels",
                "duedate", "parent", "issuelinks",
                "customfield_10014", "customfield_10008", "customfield_10100"
            ],
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        response = requests.post(
            url, json=payload, auth=(JIRA_EMAIL, JIRA_TOKEN),
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            st.error(f"Erro ao conectar com Jira: {response.status_code} — {response.text}")
            return pd.DataFrame()

        data = response.json()
        issues = data.get("issues", [])

        for issue in issues:
            f = issue["fields"]
            assignee_name = "Não atribuído"
            if f.get("assignee"):
                assignee_name = f["assignee"].get("displayName", "Não atribuído")

            all_issues.append({
                "key": issue["key"],
                "summary": f.get("summary", ""),
                "status": f["status"]["name"],
                "status_category": f["status"]["statusCategory"]["name"],
                "type": f["issuetype"]["name"],
                "is_subtask": f["issuetype"].get("subtask", False),
                "priority": (f.get("priority") or {}).get("name", "None"),
                "assignee_raw": assignee_name,
                "assignee": TEAM.get(assignee_name, {}).get("name", assignee_name),
                "created": f.get("created", "")[:10],
                "resolved": f.get("resolutiondate", "")[:10] if f.get("resolutiondate") else None,
                "updated": f.get("updated", "")[:10],
                "resolution": (f.get("resolution") or {}).get("name", None),
                "labels": f.get("labels", []),
                "duedate": f.get("duedate", None),
                "parent_key": f.get("parent", {}).get("key", None) if f.get("parent") else None,
                "parent_summary": f.get("parent", {}).get("fields", {}).get("summary", None) if f.get("parent") else None,
                "epic_link": f.get("customfield_10014", None),
                "links": [
                    {
                        "type": link.get("type", {}).get("name", ""),
                        "direction": "outward" if "outwardIssue" in link else "inward",
                        "linked_key": link.get("outwardIssue", link.get("inwardIssue", {})).get("key", ""),
                        "linked_summary": link.get("outwardIssue", link.get("inwardIssue", {})).get("fields", {}).get("summary", ""),
                        "linked_status": link.get("outwardIssue", link.get("inwardIssue", {})).get("fields", {}).get("status", {}).get("name", ""),
                        "inward_label": link.get("type", {}).get("inward", ""),
                        "outward_label": link.get("type", {}).get("outward", ""),
                    }
                    for link in f.get("issuelinks", [])
                    if "outwardIssue" in link or "inwardIssue" in link
                ],
            })

        # Pagination via nextPageToken
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    df = pd.DataFrame(all_issues)
    if not df.empty:
        df["created_dt"] = pd.to_datetime(df["created"])
        df["resolved_dt"] = pd.to_datetime(df["resolved"])
        df["updated_dt"] = pd.to_datetime(df["updated"])
        df["duedate_dt"] = pd.to_datetime(df["duedate"])
        df["lead_days"] = (df["resolved_dt"] - df["created_dt"]).dt.days

        # Build effective_epic: uses parent_key if parent is an Epic, otherwise uses epic_link
        epic_keys = set(df[df["type"] == "Epic"]["key"].tolist())
        df["effective_epic"] = df.apply(
            lambda r: r["parent_key"] if r.get("parent_key") in epic_keys
            else r.get("epic_link") if r.get("epic_link") in epic_keys
            else r.get("parent_key"),
            axis=1,
        )
    return df


def get_member_color(name):
    for _, info in TEAM.items():
        if info["name"] == name:
            return info["color"]
    return "#64748b"


# ─── CUSTOM CSS ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');

    .stApp { font-family: 'DM Sans', sans-serif; }

    .metric-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9));
        border: 1px solid rgba(148,163,184,0.1);
        border-radius: 14px;
        padding: 20px;
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .metric-card .label {
        font-size: 12px;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 500;
    }
    .metric-card .value {
        font-size: 32px;
        font-weight: 700;
        margin-top: 6px;
        font-family: 'JetBrains Mono', monospace;
    }
    .metric-card .delta {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 4px;
    }

    .person-card {
        background: rgba(30,41,59,0.6);
        border: 1px solid rgba(148,163,184,0.08);
        border-radius: 14px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .person-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;
    }
    .person-avatar {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        font-weight: 700;
        color: white;
    }
    .person-name { font-weight: 600; font-size: 15px; }
    .person-role { font-size: 12px; color: #94a3b8; }

    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 600;
    }

    .alert-card {
        background: rgba(239,68,68,0.06);
        border: 1px solid rgba(239,68,68,0.15);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    div[data-testid="stMetric"] {
        background: rgba(30,41,59,0.6);
        border: 1px solid rgba(148,163,184,0.08);
        border-radius: 12px;
        padding: 16px;
    }

    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)


# ─── MAIN APP ───
def main():
    # Header
    st.markdown("# 📊 Dashboard Kanban — Squad Plataforma")
    st.markdown(
        f"**Projeto:** SPT — Squad Plataforma | TFSports &nbsp;|&nbsp; "
        f"**Board:** [Board 376]({JIRA_URL}/jira/software/projects/SPT/boards/376) &nbsp;|&nbsp; "
        f"**Método:** Kanban"
    )

    # Fetch data
    with st.spinner("Carregando dados do Jira..."):
        df = fetch_jira_issues()

    if df.empty:
        st.error("Nenhum dado encontrado. Verifique a conexão com o Jira.")
        return

    last_updated = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.caption(f"🔄 Última atualização: {last_updated} &nbsp;|&nbsp; Total de issues: {len(df)}")

    # ─── SIDEBAR FILTERS ───
    with st.sidebar:
        st.markdown("### ⚙️ Filtros")

        type_filter = st.multiselect(
            "Tipo de Item",
            options=sorted(df["type"].unique()),
            default=sorted(df["type"].unique()),
        )

        status_filter = st.multiselect(
            "Status",
            options=[s for s in STATUS_ORDER if s in df["status"].unique()],
            default=[s for s in STATUS_ORDER if s in df["status"].unique()],
        )

        assignee_filter = st.multiselect(
            "Responsável",
            options=sorted(df["assignee"].unique()),
            default=sorted(df["assignee"].unique()),
        )

        exclude_subtasks = st.checkbox("Excluir Subtasks", value=False)

        st.markdown("---")
        st.markdown("### 👥 Squad Plataforma")
        for key, info in TEAM.items():
            st.markdown(
                f'<span style="color:{info["color"]}">●</span> **{info["name"]}** — {info["role"]}',
                unsafe_allow_html=True,
            )

        st.markdown("---")
        if st.button("🔄 Atualizar Dados", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        user = st.session_state.get("user", "")
        st.caption(f"👤 Logado como: **{user}**")
        if st.button("🚪 Sair", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state["user"] = ""
            st.rerun()

    # Apply filters
    filtered = df[
        (df["type"].isin(type_filter))
        & (df["status"].isin(status_filter))
        & (df["assignee"].isin(assignee_filter))
    ]
    if exclude_subtasks:
        filtered = filtered[~filtered["is_subtask"]]

    # ─── TABS ───
    tab1, tab_plan, tab_gantt, tab2, tab3, tab4, tab5, tab_mc = st.tabs([
        "📈 Visão Geral", "🎯 Planejados x Entregues", "📅 Timeline",
        "🔄 Fluxo", "👤 Pessoas", "🚨 Alertas", "📋 Todos os Itens", "🎲 Monte Carlo"
    ])

    # ═══════════════════════════════════════
    # TAB 1 — VISÃO GERAL
    # ═══════════════════════════════════════
    with tab1:
        # Period of analysis
        date_min = filtered["created_dt"].min()
        date_max = filtered[["created_dt", "resolved_dt", "updated_dt"]].max().max()
        period_start = date_min.strftime("%d/%m/%Y") if pd.notna(date_min) else "–"
        period_end = date_max.strftime("%d/%m/%Y") if pd.notna(date_max) else "–"
        total_weeks = max(1, ((date_max - date_min).days // 7)) if pd.notna(date_min) and pd.notna(date_max) else 0
        st.markdown(
            f'<div style="background:rgba(99,102,241,0.08); border:1px solid rgba(99,102,241,0.2); '
            f'border-radius:10px; padding:12px 18px; margin-bottom:16px; font-size:13px;">'
            f'📅 <b>Período de análise:</b> {period_start} a {period_end} '
            f'({total_weeks} semanas) &nbsp;|&nbsp; '
            f'📊 <b>Itens analisados:</b> {len(filtered)} de {len(df)} total'
            f'</div>',
            unsafe_allow_html=True,
        )

        # KPI Cards
        total = len(filtered)
        done = len(filtered[filtered["status"] == "Done"])
        wip = len(filtered[~filtered["status"].isin(["Done", "To Do", "Backlog"])])
        blocked = len(filtered[filtered["status"].isin(["Bloqueado", "BUGS"])])
        bugs_open = len(filtered[(filtered["type"] == "Bug") & (filtered["status"] != "Done")])

        done_with_lead = filtered[(filtered["status"] == "Done") & (filtered["lead_days"].notna())]
        avg_lead = f"{done_with_lead['lead_days'].mean():.1f}d" if len(done_with_lead) > 0 else "–"
        completion_rate = f"{(done / total * 100):.0f}%" if total > 0 else "0%"

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("📋 Total", total)
        c2.metric("✅ Concluídos", done)
        c3.metric("⚡ WIP", wip)
        c4.metric("🔴 Bloqueados", blocked)
        c5.metric("⏱️ Lead Time Médio", avg_lead)
        c6.metric("📈 Taxa Conclusão", completion_rate)

        st.markdown("---")

        # Charts Row 1
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Distribuição por Status")
            status_counts = filtered["status"].value_counts()
            status_df = pd.DataFrame({
                "Status": status_counts.index,
                "Quantidade": status_counts.values
            })
            # Sort by STATUS_ORDER
            status_df["order"] = status_df["Status"].map(
                {s: i for i, s in enumerate(STATUS_ORDER)}
            )
            status_df = status_df.sort_values("order").drop("order", axis=1)

            colors = [STATUS_COLORS.get(s, "#64748b") for s in status_df["Status"]]
            fig = px.bar(
                status_df, x="Quantidade", y="Status", orientation="h",
                color="Status", color_discrete_map=STATUS_COLORS,
            )
            fig.update_layout(
                showlegend=False, height=350,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans"),
                yaxis=dict(categoryorder="array", categoryarray=list(reversed(STATUS_ORDER))),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("#### Distribuição por Tipo")
            type_counts = filtered["type"].value_counts()
            fig = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                color=type_counts.index,
                color_discrete_map=TYPE_COLORS,
                hole=0.4,
            )
            fig.update_layout(
                height=350,
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans"),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Charts Row 2
        col3, col4 = st.columns(2)

        with col3:
            st.markdown("#### Throughput Semanal (itens concluídos)")
            done_items = filtered[filtered["resolved_dt"].notna()].copy()
            if not done_items.empty:
                done_items["week"] = done_items["resolved_dt"].dt.isocalendar().week
                done_items["year_week"] = done_items["resolved_dt"].dt.strftime("%Y-S%U")
                throughput = done_items.groupby("year_week").size().reset_index(name="Concluídos")
                throughput = throughput.sort_values("year_week")

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=throughput["year_week"], y=throughput["Concluídos"],
                    mode="lines+markers", fill="tozeroy",
                    line=dict(color="#10b981", width=2),
                    marker=dict(size=8),
                    fillcolor="rgba(16,185,129,0.15)",
                ))
                fig.update_layout(
                    height=350,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans"),
                    xaxis_title="Semana", yaxis_title="Itens",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum item concluído para exibir throughput.")

        with col4:
            st.markdown("#### Lead Time por Pessoa (dias)")
            if not done_with_lead.empty:
                lead_by_person = done_with_lead.groupby("assignee")["lead_days"].agg(["mean", "min", "max"]).reset_index()
                lead_by_person.columns = ["Pessoa", "Média", "Mín", "Máx"]
                lead_by_person = lead_by_person.sort_values("Média")

                colors = [get_member_color(p) for p in lead_by_person["Pessoa"]]
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=lead_by_person["Pessoa"], y=lead_by_person["Média"],
                    marker_color=colors,
                    text=[f"{v:.1f}d" for v in lead_by_person["Média"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    height=350,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans"),
                    yaxis_title="Dias",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nenhum item concluído para exibir lead time.")

        # Distribuição por Responsável
        st.markdown("#### Distribuição por Responsável")
        assignee_counts = filtered["assignee"].value_counts().reset_index()
        assignee_counts.columns = ["Pessoa", "Quantidade"]
        colors = [get_member_color(p) for p in assignee_counts["Pessoa"]]
        fig = px.bar(
            assignee_counts, x="Pessoa", y="Quantidade",
            color="Pessoa",
            color_discrete_map={p: get_member_color(p) for p in assignee_counts["Pessoa"]},
        )
        fig.update_layout(
            showlegend=False, height=300,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ═══════════════════════════════════════
    # TAB PLANEJADOS x ENTREGUES
    # ═══════════════════════════════════════
    with tab_plan:
        st.markdown("#### 🎯 Planejados x Entregues (por semana)")

        # Status legend
        st.markdown(
            '<div style="background:rgba(30,41,59,0.6); border:1px solid rgba(148,163,184,0.1); '
            'border-radius:10px; padding:14px 18px; margin-bottom:16px;">'
            '<div style="font-size:13px; font-weight:600; margin-bottom:8px; color:#e2e8f0;">📖 Legenda dos status de entrega:</div>'
            '<div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:12px;">'
            '<div><span style="color:#10b981;">✅ <b>No prazo</b></span> — Concluído (Done) antes ou no prazo</div>'
            '<div><span style="color:#f59e0b;">⚠️ <b>Com atraso</b></span> — Concluído (Done) depois do prazo</div>'
            '<div><span style="color:#ef4444;">❌ <b>Não entregue</b></span> — Prazo expirado e o item NÃO foi concluído</div>'
            '<div><span style="color:#60a5fa;">🔜 <b>Pendente</b></span> — Prazo ainda não chegou (item em andamento)</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )

        # Filter only items with duedate
        has_due = filtered[filtered["duedate_dt"].notna()].copy()

        if has_due.empty:
            st.warning("Nenhum item com Due Date definida encontrado nos filtros atuais.")
        else:
            today = pd.Timestamp.now().normalize()

            # Classify each item
            def classify_delivery(row):
                if row["status"] == "Done" and pd.notna(row["resolved_dt"]):
                    if row["resolved_dt"].normalize() <= row["duedate_dt"].normalize():
                        return "✅ No prazo"
                    else:
                        return "⚠️ Com atraso"
                elif row["duedate_dt"].normalize() < today:
                    return "❌ Não entregue"
                else:
                    return "🔜 Pendente"

            has_due["entrega"] = has_due.apply(classify_delivery, axis=1)

            # Week grouping based on duedate
            has_due["due_week"] = has_due["duedate_dt"].dt.strftime("%Y-S%U")

            # ─── KPIs de Planejados x Entregues ───
            total_planned = len(has_due[has_due["duedate_dt"].dt.normalize() <= today])
            on_time = len(has_due[has_due["entrega"] == "✅ No prazo"])
            late = len(has_due[has_due["entrega"] == "⚠️ Com atraso"])
            not_delivered = len(has_due[has_due["entrega"] == "❌ Não entregue"])
            pending = len(has_due[has_due["entrega"] == "🔜 Pendente"])
            delivered_total = on_time + late
            delivery_rate = f"{(on_time / total_planned * 100):.0f}%" if total_planned > 0 else "–"
            total_delivery_rate = f"{(delivered_total / total_planned * 100):.0f}%" if total_planned > 0 else "–"

            kc1, kc2, kc3, kc4, kc5 = st.columns(5)
            kc1.metric("🎯 Planejados (vencidos)", total_planned)
            kc2.metric("✅ No prazo", on_time)
            kc3.metric("⚠️ Com atraso", late)
            kc4.metric("❌ Não entregue", not_delivered)
            kc5.metric("📊 Taxa no prazo", delivery_rate)

            st.markdown("---")

            # ─── Gráfico semanal: Planejados x Entregues ───
            col_plan1, col_plan2 = st.columns([2, 1])

            with col_plan1:
                st.markdown("##### Planejados x Entregues por Semana")

                weekly = has_due.groupby("due_week").agg(
                    Planejados=("key", "count"),
                    No_prazo=("entrega", lambda x: (x == "✅ No prazo").sum()),
                    Com_atraso=("entrega", lambda x: (x == "⚠️ Com atraso").sum()),
                    Nao_entregue=("entrega", lambda x: (x == "❌ Não entregue").sum()),
                    Pendente=("entrega", lambda x: (x == "🔜 Pendente").sum()),
                ).reset_index().sort_values("due_week")

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=weekly["due_week"], y=weekly["Planejados"],
                    name="Planejados", marker_color="#60a5fa", opacity=0.4,
                ))
                fig.add_trace(go.Bar(
                    x=weekly["due_week"], y=weekly["No_prazo"],
                    name="No prazo", marker_color="#10b981",
                ))
                fig.add_trace(go.Bar(
                    x=weekly["due_week"], y=weekly["Com_atraso"],
                    name="Com atraso", marker_color="#f59e0b",
                ))
                fig.add_trace(go.Bar(
                    x=weekly["due_week"], y=weekly["Nao_entregue"],
                    name="Não entregue", marker_color="#ef4444",
                ))
                fig.update_layout(
                    barmode="group", height=400,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans"),
                    xaxis_title="Semana (Due Date)", yaxis_title="Itens",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02),
                )
                st.plotly_chart(fig, use_container_width=True)

            with col_plan2:
                st.markdown("##### Distribuição de Entregas")
                entrega_counts = has_due["entrega"].value_counts()
                color_map = {
                    "✅ No prazo": "#10b981",
                    "⚠️ Com atraso": "#f59e0b",
                    "❌ Não entregue": "#ef4444",
                    "🔜 Pendente": "#60a5fa",
                }
                fig = px.pie(
                    values=entrega_counts.values,
                    names=entrega_counts.index,
                    color=entrega_counts.index,
                    color_discrete_map=color_map,
                    hole=0.45,
                )
                fig.update_layout(
                    height=400,
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans"),
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # ─── Taxa de entrega no prazo por pessoa ───
            st.markdown("##### 📊 Taxa de Entrega no Prazo por Pessoa")
            due_past = has_due[has_due["duedate_dt"].dt.normalize() <= today].copy()

            if not due_past.empty:
                person_delivery = due_past.groupby("assignee").agg(
                    Planejados=("key", "count"),
                    No_prazo=("entrega", lambda x: (x == "✅ No prazo").sum()),
                    Com_atraso=("entrega", lambda x: (x == "⚠️ Com atraso").sum()),
                    Nao_entregue=("entrega", lambda x: (x == "❌ Não entregue").sum()),
                ).reset_index()
                person_delivery["Taxa no prazo"] = (
                    person_delivery["No_prazo"] / person_delivery["Planejados"] * 100
                ).round(1)
                person_delivery = person_delivery.sort_values("Taxa no prazo", ascending=False)

                colors = [get_member_color(p) for p in person_delivery["assignee"]]
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=person_delivery["assignee"],
                    y=person_delivery["Taxa no prazo"],
                    marker_color=colors,
                    text=[f"{v:.0f}%" for v in person_delivery["Taxa no prazo"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    height=350,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans"),
                    yaxis_title="% no prazo", yaxis_range=[0, 110],
                )
                st.plotly_chart(fig, use_container_width=True)

                # Table with details
                st.markdown("##### 📋 Detalhamento por Pessoa")
                display_person = person_delivery.rename(columns={
                    "assignee": "Pessoa",
                    "No_prazo": "No prazo",
                    "Com_atraso": "Com atraso",
                    "Nao_entregue": "Não entregue",
                })
                st.dataframe(
                    display_person[["Pessoa", "Planejados", "No prazo", "Com atraso", "Não entregue", "Taxa no prazo"]],
                    hide_index=True, use_container_width=True,
                )

            st.markdown("---")

            # ─── Lista detalhada ───
            st.markdown("##### 📋 Todos os Itens com Due Date")
            display_has_due = has_due[[
                "key", "summary", "status", "assignee", "duedate", "resolved", "entrega"
            ]].sort_values("duedate", ascending=False)
            display_has_due.columns = ["Key", "Resumo", "Status", "Responsável", "Due Date", "Resolvido", "Entrega"]
            st.dataframe(display_has_due, hide_index=True, use_container_width=True, height=400)

    # ═══════════════════════════════════════
    # TAB GANTT — TIMELINE ÉPICOS
    # ═══════════════════════════════════════
    with tab_gantt:
        st.markdown("#### 📅 Timeline — Épicos e Tarefas")
        st.caption("Visão hierárquica dos épicos. Cores por status: 🟢 No prazo · 🟡 Risco de atraso · 🔴 Atrasado · 🔵 Concluído")

        epics = df[df["type"] == "Epic"].copy()

        if epics.empty:
            st.warning("Nenhum épico encontrado no projeto.")
        else:
            today = pd.Timestamp.now().normalize()

            # ─── Build hierarchical data: Epic → Children ───
            timeline_rows = []

            # Semantic colors (no per-epic palette — clarity over aesthetics)
            COLOR_ON_TRACK = "#10b981"    # Green — No prazo
            COLOR_DONE = "#3b82f6"        # Blue — Concluído
            COLOR_AT_RISK = "#f59e0b"     # Yellow/Amber — Risco de atraso
            COLOR_OVERDUE = "#ef4444"     # Red — Atrasado

            epics_sorted = epics.sort_values("created_dt")

            for epic_idx, (_, epic) in enumerate(epics_sorted.iterrows()):
                # Direct children of the epic (tasks/stories linked to this epic)
                children = df[df["effective_epic"] == epic["key"]].copy()
                total_children = len(children)
                done_children = len(children[children["status"] == "Done"])

                # ─── Multi-level progress calculation ───
                # For each direct child:
                #   - If it has subtasks: its progress = done_subtasks / total_subtasks
                #   - If it has no subtasks: its progress = 1.0 if Done, 0.0 otherwise
                # Also collect ALL descendants (children + their subtasks) for display
                all_descendants = children.copy()
                progress_contributions = []

                for _, child in children.iterrows():
                    subtasks = df[df["parent_key"] == child["key"]]
                    if not subtasks.empty:
                        # Child has subtasks — calculate progress from them
                        all_descendants = pd.concat([all_descendants, subtasks], ignore_index=True)
                        sub_done = len(subtasks[subtasks["status"] == "Done"])
                        sub_total = len(subtasks)
                        progress_contributions.append(sub_done / sub_total)
                    else:
                        # No subtasks — binary: Done = 1.0, else 0.0
                        progress_contributions.append(1.0 if child["status"] == "Done" else 0.0)

                if progress_contributions:
                    progress = (sum(progress_contributions) / len(progress_contributions)) * 100
                else:
                    progress = 0

                # Also count total work items for display
                total_all = len(all_descendants)
                done_all = len(all_descendants[all_descendants["status"] == "Done"])

                # Dates
                start = epic["created_dt"]
                end = epic["duedate_dt"] if pd.notna(epic.get("duedate_dt")) else None

                if end is None or pd.isna(end):
                    children_due = children["duedate_dt"].dropna()
                    if not children_due.empty:
                        end = children_due.max()
                    else:
                        end = today + pd.Timedelta(days=30)

                if end <= start:
                    end = start + pd.Timedelta(days=14)

                # Semantic color based on risk
                elapsed_ratio = max(0, (today - start).days) / max(1, (end - start).days)
                progress_ratio = progress / 100

                if progress == 100:
                    risk = "done"
                    bar_color = COLOR_DONE
                    risk_label = "🔵 Concluído"
                elif today > end:
                    risk = "overdue"
                    bar_color = COLOR_OVERDUE
                    risk_label = "🔴 Atrasado"
                elif elapsed_ratio > 0.75 and progress_ratio < 0.75:
                    risk = "at_risk"
                    bar_color = COLOR_AT_RISK
                    risk_label = "🟡 Risco"
                else:
                    risk = "on_track"
                    bar_color = COLOR_ON_TRACK
                    risk_label = "🟢 No prazo"

                # Dependencies
                deps = []
                if isinstance(epic.get("links"), list):
                    for link in epic["links"]:
                        link_type = link.get("type", "").lower()
                        if any(kw in link_type for kw in ["block", "depend", "bloqu"]):
                            deps.append({
                                "type": link.get("outward_label", link.get("type", "")),
                                "target": link.get("linked_key", ""),
                                "target_summary": link.get("linked_summary", ""),
                            })

                # Add EPIC row
                timeline_rows.append({
                    "key": epic["key"],
                    "label": f"⚡ {epic['key']} {epic['summary'][:45]}",
                    "summary": epic["summary"],
                    "start": start,
                    "end": end,
                    "progress": progress,
                    "status": epic["status"],
                    "assignee": epic["assignee"],
                    "bar_color": bar_color,
                    "risk": risk,
                    "risk_label": risk_label,
                    "is_epic": True,
                    "total_children": total_all,
                    "done_children": done_all,
                    "dependencies": deps,
                })

                # Add CHILDREN rows — include direct children AND their subtasks
                direct_child_keys = set(children["key"].tolist())
                for _, child in all_descendants.sort_values("created_dt").iterrows():
                    c_start = child["created_dt"]
                    c_end = child["duedate_dt"] if pd.notna(child.get("duedate_dt")) else None

                    if c_end is None or pd.isna(c_end):
                        c_end = child["resolved_dt"] if pd.notna(child.get("resolved_dt")) else end

                    if pd.isna(c_end) or c_end <= c_start:
                        c_end = c_start + pd.Timedelta(days=7)

                    # Semantic color for children
                    if child["status"] == "Done":
                        c_color = COLOR_DONE
                        c_risk = "🔵"
                    elif pd.notna(child.get("duedate_dt")) and today > child["duedate_dt"]:
                        c_color = COLOR_OVERDUE
                        c_risk = "🔴"
                    elif child["status"] in ["Bloqueado", "BUGS"]:
                        c_color = COLOR_OVERDUE
                        c_risk = "🔴"
                    else:
                        c_elapsed = max(0, (today - c_start).days) / max(1, (c_end - c_start).days)
                        if c_elapsed > 0.85:
                            c_color = COLOR_AT_RISK
                            c_risk = "🟡"
                        else:
                            c_color = COLOR_ON_TRACK
                            c_risk = "🟢"

                    status_short = child["status"][:12]

                    # Determine indentation level
                    is_direct_child = child["key"] in direct_child_keys
                    if is_direct_child:
                        label = f"  ↳ {child['key']} {child['summary'][:38]}"
                    else:
                        label = f"      ↳ {child['key']} {child['summary'][:34]}"

                    timeline_rows.append({
                        "key": child["key"],
                        "label": label,
                        "summary": child["summary"],
                        "start": c_start,
                        "end": c_end,
                        "progress": 100 if child["status"] == "Done" else 0,
                        "status": child["status"],
                        "assignee": child["assignee"],
                        "bar_color": c_color,
                        "risk": c_risk,
                        "risk_label": f"{c_risk} {status_short}",
                        "is_epic": False,
                        "total_children": 0,
                        "done_children": 0,
                        "dependencies": [],
                    })

            # ─── KPIs ───
            epic_rows = [r for r in timeline_rows if r["is_epic"]]
            kc1, kc2, kc3, kc4 = st.columns(4)
            kc1.metric("🏗️ Épicos", len(epic_rows))
            avg_prog = sum(e["progress"] for e in epic_rows) / len(epic_rows) if epic_rows else 0
            kc2.metric("📊 Progresso Médio", f"{avg_prog:.0f}%")
            overdue_count = sum(1 for e in epic_rows if e["risk"] == "overdue")
            kc3.metric("🔴 Atrasados", overdue_count)
            at_risk_count = sum(1 for e in epic_rows if e["risk"] == "at_risk")
            kc4.metric("🟡 Em Risco", at_risk_count)

            st.markdown("---")

            # ─── EXPAND / COLLAPSE CONTROLS ───
            if "expanded_epics" not in st.session_state:
                st.session_state["expanded_epics"] = set()

            ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 4])
            with ctrl1:
                if st.button("➕ Expandir Todos", use_container_width=True, key="gantt_expand_all"):
                    st.session_state["expanded_epics"] = {r["key"] for r in epic_rows}
                    st.rerun()
            with ctrl2:
                if st.button("➖ Retrair Todos", use_container_width=True, key="gantt_collapse_all"):
                    st.session_state["expanded_epics"] = set()
                    st.rerun()

            # Per-epic toggles
            st.markdown("")
            toggle_cols = st.columns(min(len(epic_rows), 4))
            for i, ep in enumerate(epic_rows):
                col_idx = i % min(len(epic_rows), 4)
                is_expanded = ep["key"] in st.session_state["expanded_epics"]
                icon = "▼" if is_expanded else "▶"
                with toggle_cols[col_idx]:
                    if st.button(
                        f"{icon} {ep['key']}",
                        key=f"toggle_{ep['key']}",
                        use_container_width=True,
                        help=ep["summary"],
                    ):
                        if is_expanded:
                            st.session_state["expanded_epics"].discard(ep["key"])
                        else:
                            st.session_state["expanded_epics"].add(ep["key"])
                        st.rerun()

            st.markdown("")

            # Filter visible rows based on expand/collapse state
            visible_rows = []
            current_epic_key = None
            for row in timeline_rows:
                if row["is_epic"]:
                    current_epic_key = row["key"]
                    is_expanded = current_epic_key in st.session_state["expanded_epics"]
                    icon = "▼" if is_expanded else "▶"
                    row_copy = row.copy()
                    row_copy["label"] = f"{icon} {row['key']} {row['summary'][:45]}"
                    visible_rows.append(row_copy)
                else:
                    if current_epic_key in st.session_state["expanded_epics"]:
                        visible_rows.append(row)

            # ─── TIMELINE CHART (Jira-style) ───
            # Build DataFrame for px.timeline
            chart_data = []
            for row in visible_rows:
                chart_data.append({
                    "Task": row["label"],
                    "Start": row["start"],
                    "Finish": row["end"],
                    "Color": row["bar_color"],
                    "Epic": row["is_epic"],
                    "Key": row["key"],
                    "Status": row["status"],
                    "Progress": row["progress"],
                    "Risk": row["risk_label"],
                    "Assignee": row["assignee"],
                    "Summary": row["summary"],
                    "Children": f"{row['done_children']}/{row['total_children']}" if row["is_epic"] else "",
                })

            chart_df = pd.DataFrame(chart_data)

            if not chart_df.empty:
                fig = px.timeline(
                    chart_df,
                    x_start="Start",
                    x_end="Finish",
                    y="Task",
                    color="Task",
                    color_discrete_map={row["Task"]: row["Color"] for _, row in chart_df.iterrows()},
                    custom_data=["Key", "Status", "Progress", "Risk", "Assignee", "Summary", "Children"],
                )

                # Style the bars
                fig.update_traces(
                    marker_line_width=0,
                    opacity=0.9,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> — %{customdata[5]}<br>"
                        "Status: %{customdata[1]}<br>"
                        "Progresso: %{customdata[2]:.0f}% (%{customdata[6]})<br>"
                        "Início: %{base|%d/%m/%Y}<br>"
                        "Previsão: %{x|%d/%m/%Y}<br>"
                        "Responsável: %{customdata[4]}<br>"
                        "Risco: %{customdata[3]}"
                        "<extra></extra>"
                    ),
                )

                # Make epic bars thicker, children thinner
                for trace in fig.data:
                    task_name = trace.name
                    matching = chart_df[chart_df["Task"] == task_name]
                    if not matching.empty and matching.iloc[0]["Epic"]:
                        trace.width = 0.7
                    else:
                        trace.width = 0.45

                # Today line
                today_str = today.strftime("%Y-%m-%d")
                fig.add_shape(
                    type="line",
                    x0=today_str, x1=today_str, y0=-0.5, y1=len(visible_rows) - 0.5,
                    xref="x", yref="y",
                    line=dict(color="#60a5fa", width=2, dash="dot"),
                )
                fig.add_annotation(
                    x=today_str, y=-0.8, yref="y",
                    text=f"<b>Hoje ({today.strftime('%d/%m')})</b>",
                    showarrow=False,
                    font=dict(color="#60a5fa", size=10),
                )

                # Add progress % annotations on epic bars
                for row in visible_rows:
                    if row["is_epic"]:
                        duration = (row["end"] - row["start"]).days
                        mid = row["start"] + pd.Timedelta(days=max(1, duration) / 2)
                        fig.add_annotation(
                            x=mid.strftime("%Y-%m-%d"),
                            y=row["label"],
                            text=f"<b>{row['progress']:.0f}%</b>",
                            showarrow=False,
                            font=dict(color="white", size=11, family="DM Sans"),
                        )

                # Status badges after child bars
                for row in visible_rows:
                    if not row["is_epic"]:
                        badge_x = row["end"] + pd.Timedelta(days=1)
                        badge_text = row["status"]
                        fig.add_annotation(
                            x=badge_x.strftime("%Y-%m-%d"),
                            y=row["label"],
                            text=f"<b>{badge_text}</b>",
                            showarrow=False,
                            font=dict(color=row["bar_color"], size=9, family="DM Sans"),
                            xanchor="left",
                        )

                # Dependency arrows
                key_to_row = {r["key"]: r for r in visible_rows if r["is_epic"]}
                for row in visible_rows:
                    if row["is_epic"] and row.get("dependencies"):
                        for dep in row["dependencies"]:
                            target_key = dep["target"]
                            if target_key in key_to_row:
                                fig.add_annotation(
                                    x=row["start"].strftime("%Y-%m-%d"),
                                    y=row["label"],
                                    ax=key_to_row[target_key]["end"].strftime("%Y-%m-%d"),
                                    ay=key_to_row[target_key]["label"],
                                    xref="x", yref="y", axref="x", ayref="y",
                                    showarrow=True,
                                    arrowhead=3, arrowsize=1.2, arrowwidth=1.5,
                                    arrowcolor="#f59e0b",
                                    opacity=0.7,
                                )

                # Layout — Jira-style
                fig.update_layout(
                    height=max(350, len(visible_rows) * 46 + 100),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="DM Sans", size=11),
                    showlegend=False,
                    xaxis=dict(
                        type="date",
                        gridcolor="rgba(148,163,184,0.08)",
                        dtick="604800000",
                        tickformat="%d/%m",
                        side="top",
                        showline=False,
                        tickfont=dict(size=10, color="#94a3b8"),
                    ),
                    yaxis=dict(
                        autorange="reversed",
                        showgrid=False,
                        tickfont=dict(size=11),
                        showline=False,
                    ),
                    margin=dict(l=10, r=100, t=40, b=20),
                    bargap=0.2,
                )

                st.plotly_chart(fig, use_container_width=True)

            # ─── LEGENDA ───
            st.markdown(
                '<div style="display:flex; gap:20px; justify-content:center; font-size:12px; margin-top:-10px; flex-wrap:wrap;">'
                '<span><span style="color:#10b981;">████</span> No prazo</span>'
                '<span><span style="color:#f59e0b;">████</span> Risco de atraso</span>'
                '<span><span style="color:#ef4444;">████</span> Atrasado</span>'
                '<span><span style="color:#3b82f6;">████</span> Concluído</span>'
                '<span style="color:#60a5fa;">┆ Hoje</span>'
                '</div>',
                unsafe_allow_html=True,
            )

            # ─── DEPENDENCIES TABLE ───
            deps_exist = any(r["dependencies"] for r in timeline_rows if r["is_epic"])
            if deps_exist:
                st.markdown("---")
                st.markdown("##### 🔗 Dependências entre Épicos")
                for row in timeline_rows:
                    if row["is_epic"] and row["dependencies"]:
                        for dep in row["dependencies"]:
                            st.markdown(
                                f'<div style="background:rgba(30,41,59,0.6); border:1px solid rgba(148,163,184,0.1); '
                                f'border-radius:8px; padding:10px 14px; margin-bottom:8px; font-size:13px;">'
                                f'<span style="color:#60a5fa; font-weight:600;">{row["key"]}</span>'
                                f' <span style="color:#94a3b8;">→ {dep["type"]} →</span> '
                                f'<span style="color:#f59e0b; font-weight:600;">{dep["target"]}</span>'
                                f' <span style="color:#cbd5e1;">{dep["target_summary"][:50]}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

            # ─── DETALHAMENTO POR ÉPICO (expanders) ───
            st.markdown("---")
            st.markdown("##### 📋 Detalhamento por Épico")

            for row in timeline_rows:
                if not row["is_epic"]:
                    continue

                # Get all descendants (children + their subtasks)
                direct_children = df[df["effective_epic"] == row["key"]]
                subtasks_of_children = df[df["parent_key"].isin(direct_children["key"])]
                children_df = pd.concat([direct_children, subtasks_of_children], ignore_index=True).drop_duplicates(subset="key")
                days_remaining = (row["end"] - today).days

                with st.expander(
                    f"{row['risk_label']} **{row['key']}** — {row['summary']} &nbsp;|&nbsp; "
                    f"Progresso: {row['progress']:.0f}% ({row['done_children']}/{row['total_children']}) &nbsp;|&nbsp; "
                    f"{'⚠️ Vencido há ' + str(abs(days_remaining)) + 'd' if days_remaining < 0 else str(days_remaining) + 'd restantes'}",
                    expanded=False,
                ):
                    ec1, ec2, ec3, ec4 = st.columns(4)
                    ec1.metric("Início", row["start"].strftime("%d/%m/%Y"))
                    ec2.metric("Previsão", row["end"].strftime("%d/%m/%Y"))
                    ec3.metric("Dias Restantes", f"{days_remaining}d" if days_remaining >= 0 else f"⚠️ {abs(days_remaining)}d atraso")
                    ec4.metric("Progresso", f"{row['progress']:.0f}%")

                    # Progress bar
                    st.markdown(
                        f'<div style="background:rgba(148,163,184,0.15); border-radius:8px; height:20px; '
                        f'overflow:hidden; margin:8px 0;">'
                        f'<div style="background:{row["bar_color"]}; width:{row["progress"]}%; height:100%; '
                        f'border-radius:8px; display:flex; align-items:center; justify-content:center; '
                        f'font-size:11px; color:white; font-weight:600;">'
                        f'{row["progress"]:.0f}%</div></div>',
                        unsafe_allow_html=True,
                    )

                    if not children_df.empty:
                        st.markdown("**Tarefas filhas:**")
                        disp = children_df[["key", "summary", "status", "assignee", "type", "duedate", "resolved"]].copy()
                        disp.columns = ["Key", "Resumo", "Status", "Responsável", "Tipo", "Due Date", "Resolvido"]
                        st.dataframe(disp, hide_index=True, use_container_width=True)
                    else:
                        st.info("Nenhuma tarefa filha vinculada.")

                    if row["dependencies"]:
                        st.markdown("**Dependências:**")
                        for dep in row["dependencies"]:
                            st.markdown(f"- {dep['type']} → **{dep['target']}** ({dep['target_summary'][:50]})")

            # ─── DIAGNÓSTICO DE VÍNCULOS ───
            st.markdown("---")
            with st.expander("🔍 Diagnóstico de Vínculos — Por que alguns épicos não mostram progresso?", expanded=False):
                st.markdown(
                    "O dashboard calcula progresso em **3 níveis**: Épico → Task/Story → Subtask. "
                    "Se uma Task tem subtasks, o progresso dela é calculado pela % de subtasks concluídas."
                )
                st.markdown(
                    '**Formas de vínculo:**\n'
                    '1. **Campo `parent`** — quando a task foi criada **dentro** do épico (hierarquia nativa)\n'
                    '2. **Campo `Epic Link`** — quando o épico foi selecionado no campo "Epic Link" da issue\n'
                    '3. **Subtasks** — são detectadas pelo campo `parent` apontando para uma task filha do épico'
                )

                st.markdown("---")

                non_epics = df[df["type"] != "Epic"]
                epic_keys_set = set(epics["key"].tolist())

                for _, epic_row in epics_sorted.iterrows():
                    # Direct children
                    direct = non_epics[non_epics["effective_epic"] == epic_row["key"]]
                    # Subtasks of direct children
                    subs = df[df["parent_key"].isin(direct["key"])]
                    all_desc = pd.concat([direct, subs], ignore_index=True).drop_duplicates(subset="key")

                    total = len(all_desc)
                    done = len(all_desc[all_desc["status"] == "Done"])

                    # Recalculate weighted progress
                    progress_parts = []
                    for _, ch in direct.iterrows():
                        ch_subs = df[df["parent_key"] == ch["key"]]
                        if not ch_subs.empty:
                            sub_done = len(ch_subs[ch_subs["status"] == "Done"])
                            progress_parts.append(f"{ch['key']}={sub_done}/{len(ch_subs)} subtasks")
                        else:
                            progress_parts.append(f"{ch['key']}={'Done ✅' if ch['status'] == 'Done' else ch['status']}")

                    color = "🟢" if total > 0 else "🔴"
                    st.markdown(
                        f"**{color} {epic_row['key']} — {epic_row['summary']}** &nbsp;|&nbsp; "
                        f"Descendentes: **{total}** (diretos: {len(direct)}, subtasks: {len(subs)}, Done: {done})"
                    )

                    if progress_parts:
                        st.caption("Cálculo: " + " | ".join(progress_parts))

                    if total > 0:
                        detail_data = []
                        for _, child in all_desc.iterrows():
                            # Determine level
                            is_direct = child["key"] in set(direct["key"])
                            found_via = []
                            if is_direct:
                                if child.get("parent_key") == epic_row["key"]:
                                    found_via.append("✅ parent → Epic")
                                if child.get("epic_link") == epic_row["key"]:
                                    found_via.append("✅ Epic Link")
                            else:
                                found_via.append(f"✅ subtask de {child.get('parent_key', '?')}")

                            detail_data.append({
                                "Key": child["key"],
                                "Resumo": child["summary"][:50],
                                "Tipo": child.get("type", "?"),
                                "Status": child["status"],
                                "Nível": "📋 Direto" if is_direct else "📎 Subtask",
                                "Vínculo": " + ".join(found_via) if found_via else "❓",
                                "parent_key": child.get("parent_key", "—") or "—",
                                "epic_link": child.get("epic_link", "—") or "—",
                            })
                        st.dataframe(pd.DataFrame(detail_data), hide_index=True, use_container_width=True)
                    else:
                        st.caption("⚠️ Nenhuma tarefa vinculada. Verifique no Jira se as tasks têm o campo 'Parent' ou 'Epic Link' apontando para este épico.")

                # Orphan tasks
                st.markdown("---")
                st.markdown("##### 👻 Tarefas Órfãs (sem vínculo com nenhum épico)")
                # Tasks that aren't direct children of any epic AND aren't subtasks of epic children
                all_epic_direct_children = non_epics[non_epics["effective_epic"].isin(epic_keys_set)]
                all_subtasks_of_children = df[df["parent_key"].isin(all_epic_direct_children["key"])]
                all_linked = set(all_epic_direct_children["key"]).union(set(all_subtasks_of_children["key"])).union(epic_keys_set)
                orphans = df[~df["key"].isin(all_linked)]
                if not orphans.empty:
                    orphan_data = orphans[["key", "summary", "status", "type", "assignee", "parent_key", "epic_link"]].copy()
                    orphan_data.columns = ["Key", "Resumo", "Status", "Tipo", "Responsável", "parent_key", "epic_link"]
                    st.dataframe(orphan_data, hide_index=True, use_container_width=True)
                    st.caption(
                        "Estas tarefas não aparecem em nenhum épico na Timeline. "
                        "Para corrigir, abra cada uma no Jira e preencha o campo **Epic Link** ou mova como filha de um épico."
                    )
                else:
                    st.success("Todas as tarefas estão vinculadas a um épico!")

    # ═══════════════════════════════════════
    # TAB 2 — FLUXO
    # ═══════════════════════════════════════
    with tab2:
        st.markdown("#### 🔄 Visão do Board Kanban")

        # Kanban columns
        active_statuses = [s for s in STATUS_ORDER if s in filtered["status"].unique()]
        cols = st.columns(len(active_statuses))

        for i, status in enumerate(active_statuses):
            with cols[i]:
                items = filtered[filtered["status"] == status]
                color = STATUS_COLORS.get(status, "#64748b")

                st.markdown(
                    f'<div style="background:{color}20; border-bottom:3px solid {color}; '
                    f'padding:8px 12px; border-radius:8px 8px 0 0; text-align:center;">'
                    f'<span style="color:{color}; font-weight:600; font-size:13px;">{status}</span>'
                    f'<span style="background:{color}; color:#0f172a; padding:2px 8px; '
                    f'border-radius:10px; font-size:11px; font-weight:700; margin-left:8px;">'
                    f'{len(items)}</span></div>',
                    unsafe_allow_html=True,
                )

                for _, item in items.head(10).iterrows():
                    member_color = get_member_color(item["assignee"])
                    st.markdown(
                        f'<div style="background:rgba(15,23,42,0.5); border:1px solid rgba(148,163,184,0.08); '
                        f'border-left:3px solid {member_color}; border-radius:6px; padding:8px 10px; '
                        f'margin:4px 0; font-size:12px;">'
                        f'<div style="color:#94a3b8; font-size:10px;">{item["key"]}</div>'
                        f'<div style="margin-top:2px;">{item["summary"][:45]}</div>'
                        f'<div style="color:{member_color}; font-size:10px; margin-top:3px;">{item["assignee"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                if len(items) > 10:
                    st.caption(f"+{len(items) - 10} mais")

        # CFD (Cumulative Flow Diagram)
        st.markdown("---")
        st.markdown("#### 📊 Cumulative Flow Diagram (CFD)")

        if not df.empty:
            date_range = pd.date_range(
                start=df["created_dt"].min(),
                end=datetime.now(),
                freq="D"
            )

            cfd_data = []
            for date in date_range:
                row = {"Data": date}
                for status in STATUS_ORDER:
                    created_before = df[
                        (df["created_dt"] <= date) &
                        (df["status"] == status)
                    ]
                    row[status] = len(created_before)
                cfd_data.append(row)

            cfd_df = pd.DataFrame(cfd_data)

            def hex_to_rgba(hex_color, alpha=0.25):
                """Convert hex color to rgba string for Plotly."""
                h = hex_color.lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                return f"rgba({r},{g},{b},{alpha})"

            fig = go.Figure()
            for status in reversed(STATUS_ORDER):
                if status in cfd_df.columns and cfd_df[status].sum() > 0:
                    color = STATUS_COLORS.get(status, "#64748b")
                    fig.add_trace(go.Scatter(
                        x=cfd_df["Data"], y=cfd_df[status],
                        mode="lines", stackgroup="one",
                        name=status,
                        line=dict(color=color, width=0.5),
                        fillcolor=hex_to_rgba(color, 0.25),
                    ))

            fig.update_layout(
                height=400,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans"),
                xaxis_title="Data", yaxis_title="Itens Acumulados",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig, use_container_width=True)

    # ═══════════════════════════════════════
    # TAB 3 — PESSOAS
    # ═══════════════════════════════════════
    with tab3:
        st.markdown("#### 👤 Métricas por Membro da Squad")

        # Period
        p_date_min = filtered["created_dt"].min()
        p_date_max = filtered[["created_dt", "resolved_dt", "updated_dt"]].max().max()
        p_start = p_date_min.strftime("%d/%m/%Y") if pd.notna(p_date_min) else "–"
        p_end = p_date_max.strftime("%d/%m/%Y") if pd.notna(p_date_max) else "–"
        st.markdown(
            f'<div style="background:rgba(99,102,241,0.08); border:1px solid rgba(99,102,241,0.2); '
            f'border-radius:10px; padding:12px 18px; margin-bottom:16px; font-size:13px;">'
            f'📅 <b>Período de análise:</b> {p_start} a {p_end} &nbsp;|&nbsp; '
            f'📊 <b>Itens analisados:</b> {len(filtered)}'
            f'</div>',
            unsafe_allow_html=True,
        )

        for key, info in TEAM.items():
            member_items = filtered[filtered["assignee"] == info["name"]]
            if member_items.empty:
                continue

            done_count = len(member_items[member_items["status"] == "Done"])
            wip_count = len(member_items[~member_items["status"].isin(["Done", "To Do", "Backlog"])])
            member_leads = member_items[member_items["lead_days"].notna()]
            avg_lead_member = f"{member_leads['lead_days'].mean():.1f}d" if len(member_leads) > 0 else "–"

            with st.expander(f"{'●'} **{info['name']}** — {info['role']} &nbsp;|&nbsp; Total: {len(member_items)} &nbsp;|&nbsp; Done: {done_count} &nbsp;|&nbsp; WIP: {wip_count} &nbsp;|&nbsp; Lead: {avg_lead_member}", expanded=False):
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Total", len(member_items))
                mc2.metric("Done", done_count)
                mc3.metric("WIP", wip_count)
                mc4.metric("Lead Time", avg_lead_member)

                active_items = member_items[~member_items["status"].isin(["Done", "To Do", "Backlog"])]
                if not active_items.empty:
                    st.markdown("**Itens ativos:**")
                    st.dataframe(
                        active_items[["key", "summary", "status", "priority", "created", "updated"]]
                        .sort_values("status"),
                        hide_index=True,
                        use_container_width=True,
                    )

                done_items_member = member_items[member_items["status"] == "Done"].head(10)
                if not done_items_member.empty:
                    st.markdown("**Últimos concluídos:**")
                    st.dataframe(
                        done_items_member[["key", "summary", "priority", "created", "resolved", "lead_days"]]
                        .sort_values("resolved", ascending=False),
                        hide_index=True,
                        use_container_width=True,
                    )

    # ═══════════════════════════════════════
    # TAB 4 — ALERTAS
    # ═══════════════════════════════════════
    with tab4:
        st.markdown("#### 🚨 Alertas e Saúde do Board")

        # Blocked items
        blocked_items = filtered[filtered["status"].isin(["Bloqueado", "BUGS"])]
        st.markdown(f"##### 🔴 Itens Bloqueados ({len(blocked_items)})")
        if not blocked_items.empty:
            st.dataframe(
                blocked_items[["key", "summary", "status", "assignee", "priority", "created", "updated"]],
                hide_index=True, use_container_width=True,
            )
        else:
            st.success("Nenhum item bloqueado!")

        st.markdown("---")

        # Unassigned
        unassigned = filtered[(filtered["assignee"] == "Não atribuído") & (filtered["status"] != "Done")]
        st.markdown(f"##### ⚠️ Itens sem Responsável ({len(unassigned)})")
        if not unassigned.empty:
            st.dataframe(
                unassigned[["key", "summary", "status", "type", "priority", "created"]],
                hide_index=True, use_container_width=True,
            )
        else:
            st.success("Todos os itens têm responsável!")

        st.markdown("---")

        # Stale items (>7 days without update in active status)
        seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        stale = filtered[
            (~filtered["status"].isin(["Done", "To Do", "Backlog"]))
            & (filtered["updated"] <= seven_days_ago)
        ]
        st.markdown(f"##### ⏰ Itens Parados há +7 dias ({len(stale)})")
        if not stale.empty:
            st.dataframe(
                stale[["key", "summary", "status", "assignee", "priority", "updated"]].sort_values("updated"),
                hide_index=True, use_container_width=True,
            )
        else:
            st.success("Nenhum item parado por mais de 7 dias!")

        st.markdown("---")

        # Epics
        epics = filtered[filtered["type"] == "Epic"]
        st.markdown(f"##### 🏗️ Épicos ({len(epics)})")
        if not epics.empty:
            st.dataframe(
                epics[["key", "summary", "status", "priority", "created", "updated"]],
                hide_index=True, use_container_width=True,
            )

    # ═══════════════════════════════════════
    # TAB 5 — TODOS OS ITENS
    # ═══════════════════════════════════════
    with tab5:
        st.markdown(f"#### 📋 Todos os Itens ({len(filtered)})")

        # Search
        search = st.text_input("🔍 Buscar por key ou resumo", "")
        display_df = filtered.copy()
        if search:
            display_df = display_df[
                display_df["key"].str.contains(search, case=False, na=False)
                | display_df["summary"].str.contains(search, case=False, na=False)
            ]

        st.dataframe(
            display_df[[
                "key", "type", "status", "assignee", "priority",
                "created", "resolved", "lead_days", "summary"
            ]].sort_values("created", ascending=False),
            hide_index=True,
            use_container_width=True,
            height=600,
        )

    # ═══════════════════════════════════════
    # TAB MONTE CARLO
    # ═══════════════════════════════════════
    with tab_mc:
        st.markdown("#### 🎲 Simulação Monte Carlo — Previsibilidade Kanban")

        # Tutorial
        with st.expander("📚 Tutorial — Como usar esta aba (clique para abrir)", expanded=False):
            st.markdown(
                "### O que é Monte Carlo?\n"
                "É uma técnica de simulação que usa o **histórico real de entregas** da squad para prever prazos futuros "
                "de forma probabilística. Em vez de chutar um prazo, ela roda **10.000 cenários** e te diz a probabilidade de cada resultado."
            )
            st.markdown("### Como usar em 3 passos:")
            st.markdown(
                '**Passo 1 — Escolha o tipo de pergunta:**\n'
                '- 📅 **"Quando N itens serão entregues?"** → Você informa quantos itens precisa entregar. A simulação te diz a data provável.\n'
                '- 📦 **"Quantos itens até uma data?"** → Você escolhe uma data. A simulação te diz quantos itens a squad consegue entregar até lá.'
            )
            st.markdown(
                '**Passo 2 — Preencha o parâmetro:**\n'
                '- No modo 📅: informe a quantidade de itens (já vem pré-preenchido com os itens pendentes da squad)\n'
                '- No modo 📦: selecione a data alvo no calendário'
            )
            st.markdown(
                '**Passo 3 — Leia os resultados pelos percentis:**\n'
                '- **50%** → Metade das simulações terminou antes. Use como referência otimista.\n'
                '- **70%** → Boa previsão para comunicação **interna** com o time.\n'
                '- **85%** → Previsão confiável para **compromissos com stakeholders e liderança**. ⭐ Recomendado.\n'
                '- **95%** → Cenário conservador. Quase certeza de entrega.'
            )
            st.markdown("### Exemplo prático:")
            st.markdown(
                "Se a squad precisa entregar **15 itens** e o throughput médio é 5/semana, o Monte Carlo pode mostrar:\n"
                "- 50% de confiança → 3 semanas\n"
                "- 85% de confiança → 5 semanas ← **use este para comprometer com a liderança**\n"
                "- 95% de confiança → 7 semanas"
            )
            st.markdown("### Dicas:")
            st.markdown(
                "- Quanto **mais dados históricos** a squad tiver, mais precisa é a simulação\n"
                "- Se o throughput é **muito irregular** (desvio padrão alto), a faixa entre 50% e 95% será grande — isso é um sinal de que o fluxo precisa ser estabilizado\n"
                "- Use o gráfico de **Throughput Histórico** para identificar semanas atípicas (férias, emergências)"
            )

        st.markdown("")
        st.caption(
            "Simulação probabilística baseada no throughput histórico da squad. "
            "Roda 10.000 simulações para prever prazos com diferentes níveis de confiança."
        )

        # ─── Calculate historical weekly throughput ───
        done_items = df[(df["status"] == "Done") & (df["resolved_dt"].notna())].copy()

        if len(done_items) < 3:
            st.warning("Dados insuficientes para Monte Carlo. Pelo menos 3 itens concluídos são necessários.")
        else:
            # Group by week
            done_items["resolved_week"] = done_items["resolved_dt"].dt.isocalendar().week
            done_items["resolved_year"] = done_items["resolved_dt"].dt.isocalendar().year
            done_items["year_week"] = done_items["resolved_dt"].dt.strftime("%Y-S%U")

            weekly_throughput = done_items.groupby("year_week").size().reset_index(name="count")
            weekly_throughput = weekly_throughput.sort_values("year_week")

            # Fill in weeks with 0 throughput
            if len(weekly_throughput) > 1:
                all_weeks = pd.date_range(
                    start=done_items["resolved_dt"].min(),
                    end=done_items["resolved_dt"].max(),
                    freq="W-MON",
                )
                all_week_labels = [d.strftime("%Y-S%U") for d in all_weeks]
                full_throughput = pd.DataFrame({"year_week": all_week_labels})
                full_throughput = full_throughput.merge(weekly_throughput, on="year_week", how="left").fillna(0)
                throughput_values = full_throughput["count"].astype(int).tolist()
            else:
                throughput_values = weekly_throughput["count"].tolist()

            # Remove first and last week (may be incomplete)
            if len(throughput_values) > 2:
                throughput_values = throughput_values[1:-1]

            if not throughput_values:
                throughput_values = [done_items.shape[0]]

            # ─── Throughput Summary ───
            avg_tp = np.mean(throughput_values)
            med_tp = np.median(throughput_values)
            min_tp = min(throughput_values)
            max_tp = max(throughput_values)
            std_tp = np.std(throughput_values)

            kc1, kc2, kc3, kc4, kc5 = st.columns(5)
            kc1.metric("📊 Throughput Médio", f"{avg_tp:.1f}/sem")
            kc2.metric("📊 Mediana", f"{med_tp:.0f}/sem")
            kc3.metric("⬇️ Mínimo", f"{min_tp:.0f}/sem")
            kc4.metric("⬆️ Máximo", f"{max_tp:.0f}/sem")
            kc5.metric("📐 Desvio Padrão", f"{std_tp:.1f}")

            st.markdown("---")

            # ─── Throughput History Chart ───
            st.markdown("##### 📊 Throughput Histórico (itens/semana)")
            tp_chart = pd.DataFrame({"Semana": range(1, len(throughput_values) + 1), "Itens": throughput_values})
            fig_tp = go.Figure()
            fig_tp.add_trace(go.Bar(
                x=tp_chart["Semana"], y=tp_chart["Itens"],
                marker_color="#6366f1", opacity=0.8,
                text=tp_chart["Itens"], textposition="outside",
            ))
            fig_tp.add_shape(
                type="line", x0=0.5, x1=len(throughput_values) + 0.5,
                y0=avg_tp, y1=avg_tp,
                line=dict(color="#f59e0b", width=2, dash="dash"),
            )
            fig_tp.add_annotation(
                x=len(throughput_values), y=avg_tp,
                text=f"Média: {avg_tp:.1f}", showarrow=False,
                font=dict(color="#f59e0b", size=11), yshift=12,
            )
            fig_tp.update_layout(
                height=280,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans"),
                xaxis_title="Semana", yaxis_title="Itens concluídos",
                margin=dict(t=20, b=40),
            )
            st.plotly_chart(fig_tp, use_container_width=True)

            st.markdown("---")

            # ─── Simulation Modes ───
            sim_mode = st.radio(
                "Tipo de simulação:",
                ["📅 Quando N itens serão entregues?", "📦 Quantos itens até uma data?"],
                horizontal=True,
            )

            NUM_SIMULATIONS = 10000
            np.random.seed(42)

            if sim_mode == "📅 Quando N itens serão entregues?":
                st.markdown("##### 📅 Quando N itens serão entregues?")
                st.caption("Simula quando um número de itens pode ser concluído, baseado no throughput histórico.")

                mc_col1, mc_col2 = st.columns([1, 2])

                with mc_col1:
                    # Count pending items for default
                    pending = len(df[~df["status"].isin(["Done", "Backlog"])])
                    n_items = st.number_input(
                        "Quantos itens?",
                        min_value=1, max_value=200, value=max(1, pending),
                        help="Quantidade de itens a entregar",
                    )

                # Run simulation
                weeks_results = []
                for _ in range(NUM_SIMULATIONS):
                    remaining = n_items
                    weeks = 0
                    while remaining > 0:
                        # Random sample from historical throughput
                        weekly = np.random.choice(throughput_values)
                        remaining -= weekly
                        weeks += 1
                        if weeks > 200:
                            break
                    weeks_results.append(weeks)

                weeks_arr = np.array(weeks_results)

                # Percentiles
                p50 = int(np.percentile(weeks_arr, 50))
                p70 = int(np.percentile(weeks_arr, 70))
                p85 = int(np.percentile(weeks_arr, 85))
                p95 = int(np.percentile(weeks_arr, 95))

                # Convert to dates
                today_date = date.today()
                date_p50 = today_date + timedelta(weeks=p50)
                date_p70 = today_date + timedelta(weeks=p70)
                date_p85 = today_date + timedelta(weeks=p85)
                date_p95 = today_date + timedelta(weeks=p95)

                with mc_col1:
                    st.markdown("---")
                    st.markdown("**Resultados:**")
                    st.markdown(
                        f'<div style="background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">50% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#6366f1;">{p50} semanas → {date_p50.strftime("%d/%m/%Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">70% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#10b981;">{p70} semanas → {date_p70.strftime("%d/%m/%Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">85% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#f59e0b;">{p85} semanas → {date_p85.strftime("%d/%m/%Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">95% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#ef4444;">{p95} semanas → {date_p95.strftime("%d/%m/%Y")}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                with mc_col2:
                    # Histogram
                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Histogram(
                        x=weeks_arr, nbinsx=max(10, p95 - p50 + 5),
                        marker_color="#6366f1", opacity=0.7,
                        name="Simulações",
                    ))

                    # Percentile lines
                    for pval, pname, pcolor in [
                        (p50, "50%", "#6366f1"),
                        (p70, "70%", "#10b981"),
                        (p85, "85%", "#f59e0b"),
                        (p95, "95%", "#ef4444"),
                    ]:
                        fig_hist.add_shape(
                            type="line", x0=pval, x1=pval, y0=0, y1=1,
                            xref="x", yref="paper",
                            line=dict(color=pcolor, width=2, dash="dash"),
                        )
                        fig_hist.add_annotation(
                            x=pval, y=1.05, yref="paper",
                            text=f"<b>P{pname}</b><br>{pval}sem",
                            showarrow=False,
                            font=dict(color=pcolor, size=10),
                        )

                    fig_hist.update_layout(
                        title=f"Distribuição: quando {n_items} itens serão entregues?",
                        height=500,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="DM Sans"),
                        xaxis_title="Semanas", yaxis_title="Frequência (simulações)",
                        showlegend=False,
                        margin=dict(t=60),
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)

            else:
                # ─── How many items by date X? ───
                st.markdown("##### 📦 Quantos itens até uma data?")
                st.caption("Simula quantos itens podem ser entregues até uma data alvo.")

                mc_col1, mc_col2 = st.columns([1, 2])

                with mc_col1:
                    target_date = st.date_input(
                        "Data alvo:",
                        value=date.today() + timedelta(weeks=4),
                        min_value=date.today() + timedelta(days=1),
                    )

                if target_date is None:
                    st.info("Selecione uma data alvo.")
                    st.stop()

                # Use ordinal to avoid any type conflicts between date objects
                try:
                    target_ord = target_date.toordinal()
                except AttributeError:
                    target_ord = target_date.date().toordinal() if hasattr(target_date, 'date') else date.today().toordinal() + 28
                today_ord = date.today().toordinal()
                days_diff = target_ord - today_ord
                weeks_until = max(1, days_diff // 7)
                target_str = target_date.strftime("%d/%m/%Y") if hasattr(target_date, 'strftime') else str(target_date)[:10]

                # Run simulation
                items_results = []
                for _ in range(NUM_SIMULATIONS):
                    total_items = 0
                    for _ in range(weeks_until):
                        total_items += np.random.choice(throughput_values)
                    items_results.append(total_items)

                items_arr = np.array(items_results)

                # Percentiles (inverted — lower percentile = fewer items = more conservative)
                ip50 = int(np.percentile(items_arr, 50))
                ip70 = int(np.percentile(items_arr, 30))  # 70% chance of delivering AT LEAST this many
                ip85 = int(np.percentile(items_arr, 15))   # 85% chance
                ip95 = int(np.percentile(items_arr, 5))    # 95% chance

                with mc_col1:
                    st.markdown("---")
                    st.markdown(f"**Resultados** ({weeks_until} semanas):")
                    st.markdown(
                        f'<div style="background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">50% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#6366f1;">≥ {ip50} itens</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">70% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#10b981;">≥ {ip70} itens</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">85% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#f59e0b;">≥ {ip85} itens</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); '
                        f'border-radius:10px; padding:16px; margin:8px 0;">'
                        f'<div style="font-size:13px; color:#94a3b8;">95% de confiança</div>'
                        f'<div style="font-size:20px; font-weight:700; color:#ef4444;">≥ {ip95} itens</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                with mc_col2:
                    # Histogram
                    fig_hist2 = go.Figure()
                    fig_hist2.add_trace(go.Histogram(
                        x=items_arr, nbinsx=30,
                        marker_color="#6366f1", opacity=0.7,
                        name="Simulações",
                    ))

                    for pval, pname, pcolor in [
                        (ip50, "50%", "#6366f1"),
                        (ip70, "70%", "#10b981"),
                        (ip85, "85%", "#f59e0b"),
                        (ip95, "95%", "#ef4444"),
                    ]:
                        fig_hist2.add_shape(
                            type="line", x0=pval, x1=pval, y0=0, y1=1,
                            xref="x", yref="paper",
                            line=dict(color=pcolor, width=2, dash="dash"),
                        )
                        fig_hist2.add_annotation(
                            x=pval, y=1.05, yref="paper",
                            text=f"<b>P{pname}</b><br>≥{pval}",
                            showarrow=False,
                            font=dict(color=pcolor, size=10),
                        )

                    fig_hist2.update_layout(
                        title=f"Distribuição: quantos itens até {target_str}?",
                        height=500,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(family="DM Sans"),
                        xaxis_title="Itens entregues", yaxis_title="Frequência (simulações)",
                        showlegend=False,
                        margin=dict(t=60),
                    )
                    st.plotly_chart(fig_hist2, use_container_width=True)

            # ─── Explanation ───
            st.markdown("---")
            with st.expander("ℹ️ Como funciona a simulação Monte Carlo?", expanded=False):
                st.markdown(
                    "A simulação Monte Carlo é uma técnica probabilística para **previsão de prazos** no Kanban. "
                    "Em vez de usar apenas a média (que pode ser enganosa), ela roda milhares de cenários aleatórios "
                    "baseados no seu histórico real de entregas."
                )
                st.markdown("**Como funciona:**")
                st.markdown(
                    f"1. O dashboard coleta o throughput semanal da squad (últimas **{len(throughput_values)} semanas**)\n"
                    f"2. Roda **{NUM_SIMULATIONS:,}** simulações, cada uma sorteando aleatoriamente um throughput de uma semana do histórico\n"
                    f"3. Para cada simulação, acumula os itens entregues até atingir a meta\n"
                    f"4. Ordena os resultados e calcula os percentis"
                )
                st.markdown("**Como interpretar os percentis:**")
                st.markdown(
                    "- **50%** — Metade das simulações terminou antes disso. É otimista.\n"
                    "- **70%** — Boa previsão para comunicação interna.\n"
                    "- **85%** — Previsão confiável para comprometimento com stakeholders.\n"
                    "- **95%** — Cenário mais conservador. Quase certeza.\n\n"
                    "**Recomendação:** Use **85%** para compromissos com liderança e **70%** para metas internas."
                )

    # ─── FOOTER ───
    st.markdown("---")
    st.markdown(
        f'<div style="text-align:center; font-size:12px; color:#64748b;">'
        f'Squad Plataforma | TFSports • Projeto SPT • Board 376 • '
        f'Dados: Jira trackfield.atlassian.net • Atualizado: {last_updated}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── AUTHENTICATION (Senha simples via secrets) ───
def check_password():
    """Tela de login simples. Retorna True se autenticado."""

    if st.session_state.get("authenticated"):
        return True

    st.markdown(
        """
        <div style="display:flex; justify-content:center; margin-top:80px;">
            <div style="text-align:center;">
                <h1>📊 Dashboard Kanban</h1>
                <h3 style="color:#94a3b8; font-weight:400;">Squad Plataforma | TFSports</h3>
                <p style="color:#64748b; margin-top:20px;">Digite suas credenciais para acessar o painel.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("")
        with st.form("login_form"):
            username = st.text_input("👤 Usuário", placeholder="Digite seu usuário")
            password = st.text_input("🔒 Senha", type="password", placeholder="Digite sua senha")
            submitted = st.form_submit_button("Entrar", use_container_width=True, type="primary")

            if submitted:
                valid_users = st.secrets.get("auth", {}).get("users", {})
                if username in valid_users and valid_users[username] == password:
                    st.session_state["authenticated"] = True
                    st.session_state["user"] = username
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos.")

        st.caption("Acesso restrito à equipe TFSports.")

    return False


if __name__ == "__main__":
    if check_password():
        main()
