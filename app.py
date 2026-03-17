import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
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
    "hgp": {"name": "Guilherme", "role": "FullStack Dev", "color": "#6366f1"},
    "gfm": {"name": "Guedes", "role": "Backend Dev", "color": "#f59e0b"},
    "Leonardo Almeida": {"name": "Leonardo", "role": "QA Automação", "color": "#10b981"},
    "Marcelo Oliveira": {"name": "Marcelo", "role": "Eng. Backend", "color": "#ef4444"},
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
    """Busca todas as issues do projeto SPT via Jira API."""
    all_issues = []
    start_at = 0
    max_results = 100

    while True:
        url = f"{JIRA_URL}/rest/api/3/search"
        params = {
            "jql": f"project = {PROJECT_KEY} ORDER BY created DESC",
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "summary,status,issuetype,priority,assignee,created,resolutiondate,updated,resolution,labels,duedate",
        }
        response = requests.get(url, params=params, auth=(JIRA_EMAIL, JIRA_TOKEN))

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
            })

        if start_at + max_results >= data.get("total", 0):
            break
        start_at += max_results

    df = pd.DataFrame(all_issues)
    if not df.empty:
        df["created_dt"] = pd.to_datetime(df["created"])
        df["resolved_dt"] = pd.to_datetime(df["resolved"])
        df["updated_dt"] = pd.to_datetime(df["updated"])
        df["duedate_dt"] = pd.to_datetime(df["duedate"])
        df["lead_days"] = (df["resolved_dt"] - df["created_dt"]).dt.days
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

    # Apply filters
    filtered = df[
        (df["type"].isin(type_filter))
        & (df["status"].isin(status_filter))
        & (df["assignee"].isin(assignee_filter))
    ]
    if exclude_subtasks:
        filtered = filtered[~filtered["is_subtask"]]

    # ─── TABS ───
    tab1, tab_plan, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Visão Geral", "🎯 Planejados x Entregues", "🔄 Fluxo", "👤 Pessoas", "🚨 Alertas", "📋 Todos os Itens"
    ])

    # ═══════════════════════════════════════
    # TAB 1 — VISÃO GERAL
    # ═══════════════════════════════════════
    with tab1:
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
        st.caption("Itens com **Due Date** definida no Jira. Planejado = due date cai na semana. Entregue = concluído até a due date.")

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
            total_planned = len(has_due[has_due["duedate_dt"].normalize() <= today])
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
            due_past = has_due[has_due["duedate_dt"].normalize() <= today].copy()

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

            fig = go.Figure()
            for status in reversed(STATUS_ORDER):
                if status in cfd_df.columns and cfd_df[status].sum() > 0:
                    fig.add_trace(go.Scatter(
                        x=cfd_df["Data"], y=cfd_df[status],
                        mode="lines", stackgroup="one",
                        name=status,
                        line=dict(color=STATUS_COLORS.get(status, "#64748b"), width=0.5),
                        fillcolor=STATUS_COLORS.get(status, "#64748b") + "40",
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

    # ─── FOOTER ───
    st.markdown("---")
    st.markdown(
        f'<div style="text-align:center; font-size:12px; color:#64748b;">'
        f'Squad Plataforma | TFSports • Projeto SPT • Board 376 • '
        f'Dados: Jira trackfield.atlassian.net • Atualizado: {last_updated}'
        f'</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
