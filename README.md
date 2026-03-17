# 📊 Dashboard Kanban — Squad Plataforma | TFSports

Dashboard de métricas Kanban em tempo real para a Squad Plataforma (projeto SPT), conectado à API do Jira via trackfield.atlassian.net.

## 📦 Estrutura do Projeto

```
streamlit-spt/
├── app.py                    # App principal
├── requirements.txt          # Dependências
├── secrets.toml.example      # Modelo de configuração (NÃO commitar o real)
├── .gitignore
├── .streamlit/
│   └── config.toml           # Tema dark + configurações
└── README.md
```

## 🚀 Deploy no Streamlit Cloud

### Passo 1 — Criar repositório no Bitbucket
1. Crie um novo repositório (ex: `dashboard-squad-plataforma`)
2. Faça push de todos os arquivos deste projeto

### Passo 2 — Conectar no Streamlit Cloud
1. Acesse [share.streamlit.io](https://share.streamlit.io)
2. Clique em "New app"
3. Conecte ao repositório do Bitbucket
4. Selecione `app.py` como arquivo principal

### Passo 3 — Configurar Secrets
No Streamlit Cloud, vá em **Settings → Secrets** e cole:

```toml
[jira]
email = "seu-email@tfsports.com.br"
api_token = "seu-api-token-aqui"
```

Para gerar o API Token:
1. Acesse https://id.atlassian.com/manage-profile/security/api-tokens
2. Clique em "Create API token"
3. Nomeie como "streamlit-dashboard"
4. Copie o token

### Passo 4 — Deploy!
Clique em "Deploy" e aguarde o build (~2 minutos).

## 📊 Métricas Disponíveis

- **KPIs**: Total, Concluídos, WIP, Bloqueados, Lead Time Médio, Taxa de Conclusão
- **Gráficos**: Status, Tipo, Throughput Semanal, Lead Time por Pessoa, CFD
- **Visão por Pessoa**: Métricas individuais com itens ativos e concluídos
- **Alertas**: Bloqueados, sem responsável, parados há +7 dias
- **Filtros**: Por tipo, status, responsável, com opção de excluir subtasks

## 🔧 Desenvolvimento Local

```bash
pip install -r requirements.txt
cp secrets.toml.example .streamlit/secrets.toml
# Edite .streamlit/secrets.toml com suas credenciais
streamlit run app.py
```
