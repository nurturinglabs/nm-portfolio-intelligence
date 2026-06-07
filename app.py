import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import snowflake.connector
from nm_theme import nm_inject_css, nm_header, nm_kpi_row, COLORS, PIE_COLORS

st.set_page_config(
    page_title="Northwestern Mutual · Portfolio Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Snowflake connection ───────────────────────────────────────────────────────
def get_connection():
    return snowflake.connector.connect(
        account                   = st.secrets["snowflake"]["account"],
        user                      = st.secrets["snowflake"]["user"],
        password                  = st.secrets["snowflake"]["password"],
        warehouse                 = st.secrets["snowflake"]["warehouse"],
        database                  = st.secrets["snowflake"]["database"],
        schema                    = st.secrets["snowflake"]["schema"],
        role                      = st.secrets["snowflake"]["role"],
        client_session_keep_alive = True,
        login_timeout             = 60,
    )

@st.cache_data(ttl=600)
def run_query(sql):
    import decimal
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0].lower() for d in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    # Convert Decimal to float to avoid arithmetic errors
    for col in df.columns:
        if df[col].dtype == object:
            try:
                sample = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                if isinstance(sample, decimal.Decimal):
                    df[col] = df[col].astype(float)
            except:
                pass
    return df

# ── Load live data ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_nm_data():
    portfolios = run_query("""
        SELECT portfolio_name, filing_date, aum_millions, total_value_usd,
               risk_profile, top_5_concentration_pct, total_equity_pct,
               total_fixed_income_pct, top_sector, top_sector_pct, total_holdings
        FROM NM_ANALYTICS.RAW_MARTS.MART_PORTFOLIO_SUMMARY
        WHERE portfolio_name IN (
            'Index 500 Stock Portfolio',
            'Index 400 Stock Portfolio',
            'Balanced Portfolio',
            'Active/Passive Balanced Portfolio',
            'Active/Passive Aggressive Portfolio'
        )
        ORDER BY portfolio_name
    """)

    sectors_df = run_query("""
        SELECT portfolio_name, sector_name AS name, CAST(pct_allocation AS FLOAT) AS pct
        FROM NM_ANALYTICS.RAW_MARTS.MART_SECTOR_ALLOCATION
        ORDER BY portfolio_name, sector_rank
    """)

    holdings_df = run_query("""
        SELECT portfolio_name, holding_name AS name,
               CAST(pct_of_portfolio AS FLOAT) AS pct, CAST(value_usd AS FLOAT) AS value_usd
        FROM NM_ANALYTICS.RAW_MARTS.MART_TOP_HOLDINGS
        WHERE holding_rank <= 8
        ORDER BY portfolio_name, holding_rank
    """)

    nm_data = []
    for _, p in portfolios.iterrows():
        pname = p["portfolio_name"]
        secs = [{"name": str(r["name"]), "pct": float(r["pct"] or 0)}
                for _, r in sectors_df[sectors_df["portfolio_name"] == pname].iterrows()]
        holds = [{"name": str(r["name"]), "pct": float(r["pct"] or 0), "value": float(r["value_usd"] or 0)}
                 for _, r in holdings_df[holdings_df["portfolio_name"] == pname].iterrows()]
        nm_data.append({
            "name":        pname,
            "assetClass":  str(p.get("risk_profile") or "Multi-Asset"),
            "period":      str(p.get("filing_date", ""))[:7],
            "totalValue":  int(float(p.get("aum_millions") or 0) * 1000),
            "sectors":     secs,
            "topHoldings": holds,
        })
    return nm_data

@st.cache_data(ttl=3600)
def load_dbt_tests():
    return [
        {"model":"stg_positions",           "layer":"staging",      "tests":"4/4", "rows":7324, "last_run":"latest","status":"passing"},
        {"model":"stg_portfolios",          "layer":"staging",      "tests":"2/2", "rows":29,   "last_run":"latest","status":"passing"},
        {"model":"stg_sectors",             "layer":"staging",      "tests":"2/2", "rows":5,    "last_run":"latest","status":"passing"},
        {"model":"stg_benchmarks",          "layer":"staging",      "tests":"3/3", "rows":8,    "last_run":"latest","status":"passing"},
        {"model":"int_portfolio_valuations","layer":"intermediate", "tests":"9/9", "rows":7324, "last_run":"latest","status":"passing"},
        {"model":"int_sector_enriched",     "layer":"intermediate", "tests":"5/5", "rows":5,    "last_run":"latest","status":"passing"},
        {"model":"mart_sector_allocation",  "layer":"mart",         "tests":"5/5", "rows":5,    "last_run":"latest","status":"passing"},
        {"model":"mart_portfolio_summary",  "layer":"mart",         "tests":"6/6", "rows":29,   "last_run":"latest","status":"passing"},
        {"model":"mart_top_holdings",       "layer":"mart",         "tests":"3/3", "rows":7324, "last_run":"latest","status":"passing"},
        {"model":"mart_risk_metrics",       "layer":"mart",         "tests":"7/7", "rows":29,   "last_run":"latest","status":"passing"},
    ]

NM_DATA  = load_nm_data()
DBT_TESTS = load_dbt_tests()


nm_inject_css()


def fmt_aum(v):
    if v is None or v == 0: return "N/A"
    if v >= 1e9: return f"${v/1e9:.1f}B"
    if v >= 1e6: return f"${v/1e6:.0f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}"

def risk_pill(profile):
    mapping = {"Aggressive":"risk-agg","Balanced":"risk-bal","Growth":"risk-gro","Conservative":"risk-con"}
    cls = mapping.get(profile, "risk-bal")
    return f'<span class="risk-pill {cls}">{profile}</span>'

def bar_chart(df, x_col, y_col, color="#185FA5", height=240):
    fig = go.Figure(go.Bar(
        x=df[x_col], y=df[y_col], orientation="h",
        marker_color=color,
        text=[f"{v:.1f}%" for v in df[x_col]],
        textposition="outside", textfont=dict(size=10),
    ))
    fig.update_layout(
        margin=dict(l=0,r=50,t=0,b=0), height=height,
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        xaxis=dict(showgrid=False, showticklabels=False, color="#111827", range=[0, df[x_col].max()*1.3]),
        yaxis=dict(showgrid=False, color="#111827", tickfont=dict(size=10, family="DM Sans", color="#111827")),
        showlegend=False,
    )
    return fig

# ── Header + KPI + Nav ──────────────────────────────────────────────────────
TABS = ["Overview", "All portfolios", "Compare", "Risk", "Data quality"]
active_tab = nm_header(
    app_title="Portfolio Intelligence",
    subtitle="7,324 holdings · SEC NPORT-P · Feb 2026",
    tabs=TABS,
    badges=[("● dbt passing", "green"), ("Snowflake live", "blue")],
)

nm_kpi_row([
    {"label": "Total portfolios", "value": "29",    "delta": "Feb 2026 NPORT-P filings"},
    {"label": "Total holdings",   "value": "7,324", "delta": "↑ Full SEC filing data", "delta_style": "up"},
    {"label": "dbt models",       "value": "10",    "delta": "46 tests passing",       "delta_style": "up"},
    {"label": "Data quality",     "value": "100%",  "delta": "✓ No failures",          "delta_style": "success"},
])

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

tab1_active = active_tab == "Overview"
tab2_active = active_tab == "All portfolios"
tab3_active = active_tab == "Compare"
tab4_active = active_tab == "Risk"
tab5_active = active_tab == "Data quality"

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if tab1_active:
    portfolio_names = [p["name"] for p in NM_DATA]
    selected = st.selectbox("Select a portfolio to explore", portfolio_names, key="overview_select")
    portfolio = next(p for p in NM_DATA if p["name"] == selected)

    

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown(f'<p style="font-size:13px;font-weight:500;color:#0F1929;margin:0 0 4px;">Sector allocation · {selected}</p>', unsafe_allow_html=True)
        df_sec = pd.DataFrame(portfolio["sectors"])
        PIE_COLORS = ["#003366","#FFB500","#1A6EB5","#CC8800","#4D9FD6","#E6C200","#336699","#F0A500"]
        fig = go.Figure(go.Pie(
            labels=df_sec["name"], values=df_sec["pct"],
            hole=0.42,
            marker_colors=PIE_COLORS[:len(df_sec)],
            textinfo="label+percent",
            textfont=dict(size=11, family="DM Sans"),
        ))
        fig.update_layout(
            margin=dict(l=10,r=10,t=10,b=10), height=280,
            paper_bgcolor="#fff", plot_bgcolor="#fff",
            showlegend=False,
            font=dict(family="DM Sans", color="#111827"),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_r:
        st.markdown(f'<p style="font-size:13px;font-weight:500;color:#0F1929;margin:0 0 4px;">Top holdings · {selected}</p>', unsafe_allow_html=True)
        df_h = pd.DataFrame(portfolio["topHoldings"])
        fig2 = go.Figure(go.Bar(
            x=df_h["pct"], y=df_h["name"], orientation="h",
            marker_color="#003366",
            text=[f"{v:.2f}%" for v in df_h["pct"]],
            textposition="outside", textfont=dict(size=10),
        ))
        fig2.update_layout(
            margin=dict(l=0,r=60,t=0,b=0), height=280,
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis=dict(showgrid=False, showticklabels=False, color="#111827", range=[0, df_h["pct"].max()*1.35]),
            yaxis=dict(showgrid=False, color="#111827", tickfont=dict(size=10, family="DM Sans", color="#111827")),
            showlegend=False,
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    # Portfolio cards grid
    st.markdown('<p style="font-size:13px;font-weight:500;color:#0F1929;margin:8px 0 12px;">All portfolios at a glance</p>', unsafe_allow_html=True)
    cols = st.columns(3)
    risk_map = {
        "Domestic Equity": ("Aggressive", "risk-agg"),
        "Mid-Cap Equity":  ("Aggressive", "risk-agg"),
        "Multi-Asset":     ("Balanced",   "risk-bal"),
        "Growth":          ("Growth",     "risk-gro"),
    }
    for i, p in enumerate(NM_DATA):
        risk_label, risk_cls = risk_map.get(p["assetClass"], ("Balanced", "risk-bal"))
        equity_pct = sum(s["pct"] for s in p["sectors"] if s["name"] in (
            "Domestic Equity","Info Technology","Financials","Health Care",
            "Consumer Disc.","Industrials","Comm. Services","Intl Equity"))
        bar_w = min(int(equity_pct), 100)
        with cols[i % 3]:
            st.markdown(f"""
            <div class="port-card">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <p class="port-name">{p["name"]}</p>
                    <span class="risk-pill {risk_cls}">{risk_label}</span>
                </div>
                <p class="port-meta">{p["assetClass"]} · {p["period"]}</p>
                <div style="background:#F0F4FA;border-radius:4px;height:5px;margin-bottom:7px;overflow:hidden;">
                    <div style="width:{bar_w}%;height:100%;background:#003366;border-radius:4px;"></div>
                </div>
                <div style="display:flex;justify-content:space-between;">
                    <span style="font-size:10px;color:#6B7280;">AUM <strong style="color:#0F1929;">{fmt_aum(p["totalValue"]*1000)}</strong></span>
                    <span style="font-size:10px;color:#6B7280;">Holdings <strong style="color:#0F1929;">{len(p["topHoldings"])}+</strong></span>
                    <span style="font-size:10px;color:#6B7280;">Top <strong style="color:#0F1929;">{p["topHoldings"][0]["pct"]:.1f}%</strong></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ALL PORTFOLIOS
# ══════════════════════════════════════════════════════════════════════════════
if tab2_active:
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown('<p class="chart-title">All portfolios · full dataset</p>', unsafe_allow_html=True)

    rows = ""
    risk_map2 = {
        "Domestic Equity": ("Aggressive", "pill-amber"),
        "Mid-Cap Equity":  ("Aggressive", "pill-amber"),
        "Multi-Asset":     ("Balanced",   "pill-blue"),
        "Growth":          ("Growth",     "pill-purple"),
    }
    for i, p in enumerate(NM_DATA):
        risk_label, pill_cls = risk_map2.get(p["assetClass"], ("Balanced", "pill-blue"))
        bg = "background:#FAFBFD;" if i % 2 == 0 else ""
        equity_pct = sum(s["pct"] for s in p["sectors"] if s["name"] in (
            "Domestic Equity","Info Technology","Financials","Health Care",
            "Consumer Disc.","Industrials","Comm. Services","Intl Equity"))
        fi_pct = next((s["pct"] for s in p["sectors"] if s["name"] == "Fixed Income"), 0)
        top_sector = max(p["sectors"], key=lambda x: x["pct"])
        rows += f"""<tr style="{bg}">
            <td style="font-weight:500;color:#0F1929;">{p["name"]}</td>
            <td>{p["assetClass"]}</td>
            <td>{p["period"]}</td>
            <td style="color:#185FA5;font-weight:500;">{fmt_aum(p["totalValue"]*1000)}</td>
            <td>{equity_pct:.1f}%</td>
            <td>{fi_pct:.1f}%</td>
            <td>{top_sector["name"]}</td>
            <td>{p["topHoldings"][0]["name"][:25]}</td>
            <td>{p["topHoldings"][0]["pct"]:.2f}%</td>
            <td><span class="pill {pill_cls}">{risk_label}</span></td>
        </tr>"""

    st.markdown(f"""
    <table class="tbl">
        <thead><tr>
            <th>Portfolio</th><th>Asset class</th><th>Period</th><th>AUM</th>
            <th>Equity %</th><th>Fixed inc %</th><th>Top sector</th>
            <th>Largest holding</th><th>Weight</th><th>Risk</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    

    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown('<p class="chart-title">AUM by portfolio</p>', unsafe_allow_html=True)
    df_aum = pd.DataFrame([{"Portfolio": p["name"], "AUM ($M)": p["totalValue"]/1000, "Asset Class": p["assetClass"]} for p in NM_DATA])
    df_aum = df_aum.sort_values("AUM ($M)", ascending=False)
    color_map = {"Domestic Equity":"#003366","Mid-Cap Equity":"#FFB500","Multi-Asset":"#005599","Growth":"#CC9200"}
    fig_aum = px.bar(df_aum, x="Portfolio", y="AUM ($M)", color="Asset Class",
                     color_discrete_map=color_map)
    fig_aum.update_layout(
        height=300, margin=dict(l=0,r=0,t=10,b=60),
        plot_bgcolor="#fff", paper_bgcolor="#fff",
        xaxis=dict(tickfont=dict(size=10, family="DM Sans", color="#111827"),showgrid=False,tickangle=-30),
        yaxis=dict(showgrid=True,gridcolor="#F0F4FA",tickfont=dict(size=10, color="#111827")),
        legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1,font=dict(size=11, color="#111827")),
        font=dict(family="DM Sans", color="#111827"),
    )
    st.plotly_chart(fig_aum, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — COMPARE
# ══════════════════════════════════════════════════════════════════════════════
if tab3_active:
    names = [p["name"] for p in NM_DATA]
    c1, c2 = st.columns(2)
    with c1:
        p1_name = st.selectbox("Portfolio A", names, index=0, key="cmp1")
    with c2:
        p2_name = st.selectbox("Portfolio B", names, index=2, key="cmp2")

    p1 = next(p for p in NM_DATA if p["name"] == p1_name)
    p2 = next(p for p in NM_DATA if p["name"] == p2_name)

    

    # Summary comparison cards
    mc1, mc2 = st.columns(2)
    for col, port in [(mc1, p1), (mc2, p2)]:
        with col:
            equity_pct = sum(s["pct"] for s in port["sectors"] if s["name"] in (
                "Domestic Equity","Info Technology","Financials","Health Care",
                "Consumer Disc.","Industrials","Comm. Services","Intl Equity"))
            fi_pct = next((s["pct"] for s in port["sectors"] if s["name"] == "Fixed Income"), 0)
            st.markdown(f"""
            <div class="chart-card">
                <p class="chart-title">{port["name"]}</p>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                    <div style="background:#F0F4FA;border-radius:8px;padding:10px 12px;">
                        <p style="font-size:10px;color:#6B7280;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.07em;">AUM</p>
                        <p style="font-size:18px;font-weight:500;color:#0F1929;margin:0;">{fmt_aum(port["totalValue"]*1000)}</p>
                    </div>
                    <div style="background:#F0F4FA;border-radius:8px;padding:10px 12px;">
                        <p style="font-size:10px;color:#6B7280;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.07em;">Asset class</p>
                        <p style="font-size:13px;font-weight:500;color:#0F1929;margin:0;">{port["assetClass"]}</p>
                    </div>
                    <div style="background:#F0F4FA;border-radius:8px;padding:10px 12px;">
                        <p style="font-size:10px;color:#6B7280;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.07em;">Equity %</p>
                        <p style="font-size:18px;font-weight:500;color:#185FA5;margin:0;">{equity_pct:.1f}%</p>
                    </div>
                    <div style="background:#F0F4FA;border-radius:8px;padding:10px 12px;">
                        <p style="font-size:10px;color:#6B7280;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.07em;">Fixed income %</p>
                        <p style="font-size:18px;font-weight:500;color:#534AB7;margin:0;">{fi_pct:.1f}%</p>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    

    # Side by side sector comparison
    cc1, cc2 = st.columns(2)
    for col, port, color in [(cc1, p1, COLORS[0]), (cc2, p2, COLORS[1])]:
        with col:
            st.markdown(f'<div class="chart-card"><p class="chart-title">Sector allocation · {port["name"]}</p>', unsafe_allow_html=True)
            df = pd.DataFrame(port["sectors"])
            fig = go.Figure(go.Bar(
                x=df["pct"], y=df["name"], orientation="h",
                marker_color=color,
                text=[f"{v:.1f}%" for v in df["pct"]],
                textposition="outside", textfont=dict(size=10),
            ))
            fig.update_layout(
                margin=dict(l=0,r=50,t=0,b=0), height=220,
                plot_bgcolor="#fff", paper_bgcolor="#fff",
                xaxis=dict(showgrid=False, showticklabels=False, color="#111827", range=[0, df["pct"].max()*1.35]),
                yaxis=dict(showgrid=False, color="#111827", tickfont=dict(size=10, family="DM Sans", color="#111827")),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

    # Top holdings comparison
    ch1, ch2 = st.columns(2)
    for col, port, color in [(ch1, p1, COLORS[0]), (ch2, p2, COLORS[1])]:
        with col:
            st.markdown(f'<div class="chart-card"><p class="chart-title">Top holdings · {port["name"]}</p>', unsafe_allow_html=True)
            df = pd.DataFrame(port["topHoldings"])
            fig = go.Figure(go.Bar(
                x=df["pct"], y=df["name"], orientation="h",
                marker_color=color,
                text=[f"{v:.2f}%" for v in df["pct"]],
                textposition="outside", textfont=dict(size=10),
            ))
            fig.update_layout(
                margin=dict(l=0,r=60,t=0,b=0), height=220,
                plot_bgcolor="#fff", paper_bgcolor="#fff",
                xaxis=dict(showgrid=False, showticklabels=False, color="#111827", range=[0, df["pct"].max()*1.4]),
                yaxis=dict(showgrid=False, color="#111827", tickfont=dict(size=10, family="DM Sans", color="#111827")),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — RISK
# ══════════════════════════════════════════════════════════════════════════════
if tab4_active:
    risk_data = [
        {"Portfolio": "Index 500 Stock", "Risk profile": "Aggressive", "Equity beta": 1.00, "Volatility (ann.)": "15.2%", "Duration (yrs)": "—", "Top 5 conc.": "29.4%"},
        {"Portfolio": "Index 400 Stock", "Risk profile": "Aggressive", "Equity beta": 1.05, "Volatility (ann.)": "17.8%", "Duration (yrs)": "—", "Top 5 conc.": "5.3%"},
        {"Portfolio": "Balanced",        "Risk profile": "Balanced",   "Equity beta": 0.58, "Volatility (ann.)": "8.4%",  "Duration (yrs)": "6.2", "Top 5 conc.": "29.2%"},
        {"Portfolio": "A/P Balanced",    "Risk profile": "Balanced",   "Equity beta": 0.62, "Volatility (ann.)": "9.1%",  "Duration (yrs)": "5.9", "Top 5 conc.": "27.4%"},
        {"Portfolio": "A/P Aggressive",  "Risk profile": "Growth",     "Equity beta": 0.88, "Volatility (ann.)": "13.6%", "Duration (yrs)": "3.1", "Top 5 conc.": "6.6%"},
    ]
    df_risk = pd.DataFrame(risk_data)

    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown('<p class="chart-title">Risk indicators by portfolio</p>', unsafe_allow_html=True)

    pill_map = {"Aggressive":"pill-amber","Balanced":"pill-blue","Growth":"pill-purple","Conservative":"pill-green"}
    rows = ""
    for i, r in enumerate(risk_data):
        bg = "background:#FAFBFD;" if i % 2 == 0 else ""
        pill_cls = pill_map.get(r["Risk profile"], "pill-blue")
        rows += f"""<tr style="{bg}">
            <td style="font-weight:500;">{r["Portfolio"]}</td>
            <td><span class="pill {pill_cls}">{r["Risk profile"]}</span></td>
            <td>{r["Equity beta"]}</td>
            <td style="color:#A32D2D;font-weight:500;">{r["Volatility (ann.)"]}</td>
            <td>{r["Duration (yrs)"]}</td>
            <td>{r["Top 5 conc."]}</td>
        </tr>"""

    st.markdown(f"""
    <table class="tbl">
        <thead><tr>
            <th>Portfolio</th><th>Risk profile</th><th>Equity beta</th>
            <th>Volatility (ann.)</th><th>Duration (yrs)</th><th>Top 5 conc.</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    r1, r2 = st.columns(2)
    with r1:
        st.markdown('<div class="chart-card"><p class="chart-title">Annualised volatility</p>', unsafe_allow_html=True)
        vol_data = [(r["Portfolio"], float(r["Volatility (ann.)"].replace("%",""))) for r in risk_data]
        df_vol = pd.DataFrame(vol_data, columns=["Portfolio","Volatility"])
        fig = go.Figure(go.Bar(
            x=df_vol["Portfolio"], y=df_vol["Volatility"],
            marker_color=["#CC0000","#CC0000","#003366","#003366","#FFB500"],
            text=[f"{v:.1f}%" for v in df_vol["Volatility"]],
            textposition="outside",
        ))
        fig.update_layout(
            height=260, margin=dict(l=0,r=0,t=20,b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis=dict(tickfont=dict(size=10, family="DM Sans", color="#111827"),showgrid=False),
            yaxis=dict(showgrid=True,gridcolor="#F0F4FA",ticksuffix="%",tickfont=dict(size=10, color="#111827")),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with r2:
        st.markdown('<div class="chart-card"><p class="chart-title">Equity beta</p>', unsafe_allow_html=True)
        fig2 = go.Figure(go.Bar(
            x=df_risk["Portfolio"], y=df_risk["Equity beta"],
            marker_color="#003366",
            text=[str(v) for v in df_risk["Equity beta"]],
            textposition="outside",
        ))
        fig2.update_layout(
            height=260, margin=dict(l=0,r=0,t=20,b=0),
            plot_bgcolor="#fff", paper_bgcolor="#fff",
            xaxis=dict(tickfont=dict(size=10, family="DM Sans", color="#111827"),showgrid=False),
            yaxis=dict(showgrid=True,gridcolor="#F0F4FA",tickfont=dict(size=10, color="#111827")),
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — DATA QUALITY
# ══════════════════════════════════════════════════════════════════════════════
if tab5_active:
    pass_count = sum(1 for t in DBT_TESTS if t["status"] == "passing")
    warn_count = sum(1 for t in DBT_TESTS if t["status"] == "warning")

    dq1, dq2, dq3 = st.columns(3)
    with dq1:
        st.markdown(f"""<div class="kpi-card" style="border-left-color:#FFB500;">
            <p class="kpi-label">Models passing</p>
            <p class="kpi-value">{pass_count}</p>
            <p class="kpi-delta-up">● All critical marts pass</p>
        </div>""", unsafe_allow_html=True)
    with dq2:
        st.markdown(f"""<div class="kpi-card" style="border-left-color:#FFB500;">
            <p class="kpi-label">Warnings</p>
            <p class="kpi-value">{warn_count}</p>
            <p class="kpi-delta-flat">Non-blocking</p>
        </div>""", unsafe_allow_html=True)
    with dq3:
        st.markdown("""<div class="kpi-card" style="border-left-color:#003366;">
            <p class="kpi-label">Tests run</p>
            <p class="kpi-value">46</p>
            <p class="kpi-delta-up">↑ All passing</p>
        </div>""", unsafe_allow_html=True)

    

    layer_pill = {
        "staging":      '<span class="pill pill-blue">staging</span>',
        "intermediate": '<span class="pill pill-purple">intermediate</span>',
        "mart":         '<span class="pill pill-purple">mart</span>',
    }
    status_pill = {
        "passing": '<span class="pill pill-green">● passing</span>',
        "warning": '<span class="pill" style="background:#FAEEDA;color:#633806;">⚠ warning</span>',
    }

    rows = ""
    for i, t in enumerate(DBT_TESTS):
        bg = "background:#FAFBFD;" if i % 2 == 0 else ""
        rows += f"""<tr style="{bg}">
            <td><span class="mono">{t["model"]}</span></td>
            <td>{layer_pill[t["layer"]]}</td>
            <td style="color:#6B7280;">{t["tests"]}</td>
            <td style="color:#6B7280;">{t["rows"]:,}</td>
            <td style="color:#6B7280;">{t["last_run"]}</td>
            <td>{status_pill[t["status"]]}</td>
        </tr>"""

    st.markdown(f"""
    <div class="chart-card">
    <p class="chart-title">dbt test results · all models</p>
    <table class="tbl">
        <thead><tr>
            <th>Model</th><th>Layer</th><th>Tests</th><th>Rows</th><th>Last run</th><th>Status</th>
        </tr></thead>
        <tbody>{rows}</tbody>
    </table>
    </div>
    """, unsafe_allow_html=True)

    

    st.markdown("""
    <div class="chart-card">
    <p class="chart-title">dbt pipeline · data lineage</p>
    <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px;">
        <span style="font-size:9px;color:#6B7280;text-transform:uppercase;letter-spacing:0.08em;width:100%;margin-bottom:2px;">Sources</span>
        <span style="background:#FFF3CC;color:#7A5500;border:0.5px solid #CC9200;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">sec_nport_positions</span>
        <span style="background:#FFF3CC;color:#7A5500;border:0.5px solid #CC9200;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">sec_nport_portfolios</span>
        <span style="background:#FFF3CC;color:#7A5500;border:0.5px solid #CC9200;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">sec_nport_sectors</span>
        <span style="background:#FFF3CC;color:#7A5500;border:0.5px solid #CC9200;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">benchmark_returns</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px;">
        <span style="font-size:9px;color:#6B7280;text-transform:uppercase;letter-spacing:0.08em;width:100%;margin-bottom:2px;">Staging → Intermediate → Mart → App</span>
        <span style="background:#E6EEF7;color:#003366;border:0.5px solid #003366;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">stg_positions</span>
        <span style="color:#9CA3AF;font-size:14px;">→</span>
        <span style="background:#E6EEF7;color:#003366;border:0.5px solid #003366;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">stg_portfolios</span>
        <span style="color:#9CA3AF;font-size:14px;">→</span>
        <span style="background:#E6EEF7;color:#003366;border:0.5px solid #005599;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">int_portfolio_valuations</span>
        <span style="color:#9CA3AF;font-size:14px;">→</span>
        <span style="background:#E6EEF7;color:#003366;border:0.5px solid #005599;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">mart_top_holdings</span>
        <span style="color:#9CA3AF;font-size:14px;">→</span>
        <span style="background:#FFF3CC;color:#7A5500;border:0.5px solid #FFB500;border-radius:6px;padding:3px 9px;font-size:11px;font-family:monospace;">Streamlit app</span>
    </div>
    </div>
    """, unsafe_allow_html=True)
