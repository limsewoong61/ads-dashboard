import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

from connectors.meta import get_meta_data
from connectors.google_ads import get_google_ads_data
from connectors.naver import get_naver_data

st.set_page_config(
    page_title="광고 통합 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* 전체 배경 */
.stApp { background-color: #0d1117; }

/* 메트릭 카드 */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #161b27 0%, #1e2535 100%);
    border: 1px solid #2a3450;
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
[data-testid="metric-container"]:hover {
    border-color: #4f8ef7;
    transition: border-color 0.2s;
}
[data-testid="stMetricLabel"] { color: #8899bb !important; font-size: 12px !important; }
[data-testid="stMetricValue"] { color: #e8f0ff !important; font-size: 22px !important; font-weight: 700 !important; }

/* 사이드바 */
[data-testid="stSidebar"] { background-color: #0a0e18 !important; border-right: 1px solid #1e2535; }

/* 구분선 */
hr { border-color: #1e2535 !important; }

/* 탭 */
[data-testid="stTabs"] button {
    color: #8899bb !important;
    font-weight: 600;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #4f8ef7 !important;
    border-bottom: 2px solid #4f8ef7 !important;
}

/* 버튼 - primary */
[data-testid="baseButton-primary"] {
    background: linear-gradient(90deg, #1877F2, #4f8ef7) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
}
/* 버튼 - secondary */
[data-testid="baseButton-secondary"] {
    background: #1e2535 !important;
    color: #8899bb !important;
    border: 1px solid #2a3450 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
[data-testid="baseButton-secondary"]:hover {
    background: #2a3450 !important;
    color: #c0d0f0 !important;
}

/* 데이터프레임 */
[data-testid="stDataFrame"] {
    border: 1px solid #2a3450 !important;
    border-radius: 10px !important;
}

/* 서브헤더 */
h2, h3 { color: #c8d8ff !important; }

/* selectbox, radio */
[data-testid="stSelectbox"] label, [data-testid="stRadio"] label { color: #8899bb !important; }
</style>
""", unsafe_allow_html=True)

CHANNEL_COLORS = {
    "META": "#1877F2",
    "Google Ads": "#EA4335",
    "NAVER": "#03C75A",
}

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 광고 대시보드")
    st.divider()

    end_default = datetime.now() - timedelta(days=1)
    start_default = end_default - timedelta(days=29)

    start_date = st.date_input("시작일", start_default)
    end_date = st.date_input("종료일", end_default)

    if start_date > end_date:
        st.error("시작일이 종료일보다 늦을 수 없습니다.")
        st.stop()

    channels = st.multiselect(
        "채널 선택",
        ["META", "Google Ads", "NAVER"],
        default=["META", "Google Ads", "NAVER"],
    )

    st.divider()
    refresh = st.button("🔄 데이터 새로고침", use_container_width=True)
    st.caption("데이터는 1시간마다 자동 갱신됩니다.")

# ── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data(start: str, end: str):
    results, errors = {}, {}

    try:
        s = st.secrets["meta"]
        results["META"] = get_meta_data(
            app_id=s["app_id"],
            app_secret=s["app_secret"],
            access_token=s["access_token"],
            ad_account_id=s["ad_account_id"],
            start_date=start,
            end_date=end,
        )
    except Exception as e:
        errors["META"] = str(e)

    try:
        g = st.secrets["google_ads"]
        results["Google Ads"] = get_google_ads_data(
            customer_id=g["customer_id"],
            start_date=start,
            end_date=end,
            credentials={
                "developer_token": g["developer_token"],
                "client_id": g["client_id"],
                "client_secret": g["client_secret"],
                "refresh_token": g["refresh_token"],
                "use_proto_plus": True,
            },
        )
    except Exception as e:
        errors["Google Ads"] = str(e)

    try:
        n = st.secrets["naver"]
        results["NAVER"] = get_naver_data(
            api_key=n["api_key"],
            secret_key=n["secret_key"],
            customer_id=str(n["customer_id"]),
            start_date=start,
            end_date=end,
        )
    except Exception as e:
        errors["NAVER"] = str(e)

    return results, errors


if refresh:
    st.cache_data.clear()

with st.spinner("데이터 불러오는 중..."):
    all_data, load_errors = load_all_data(str(start_date), str(end_date))

# ── Error banners ─────────────────────────────────────────────────────────────

for ch, err in load_errors.items():
    st.error(f"⚠️ **{ch}** 연결 오류: {err}")

active_data = {ch: df for ch, df in all_data.items() if ch in channels and not df.empty}

if not active_data:
    st.warning("표시할 데이터가 없습니다. 채널 선택 또는 날짜 범위를 확인해주세요.")
    st.stop()

combined = pd.concat(
    [df.assign(channel=ch) for ch, df in active_data.items()],
    ignore_index=True,
)
# 날짜 없는 행 제거 (NAVER 집계 행 등)
combined = combined[combined["date"].notna() & (combined["date"].astype(str).str.match(r"\d{4}-\d{2}-\d{2}"))]

# ── Page Header ───────────────────────────────────────────────────────────────

st.title("📊 광고 통합 대시보드")
period_label = f"{start_date.strftime('%Y.%m.%d')} ~ {end_date.strftime('%Y.%m.%d')}"
active_labels = " · ".join(
    f"<span style='color:{CHANNEL_COLORS[ch]}'>{ch}</span>" for ch in active_data
)
st.markdown(f"**조회 기간:** {period_label} &nbsp;|&nbsp; **채널:** {active_labels}", unsafe_allow_html=True)
st.divider()

# ── KPI Summary ───────────────────────────────────────────────────────────────

st.subheader("전체 요약")

total_impressions = combined["impressions"].sum()
total_clicks = combined["clicks"].sum()
total_spend = combined["spend"].sum()
total_conversions = combined["conversions"].sum()
total_revenue = combined["revenue"].sum()
overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
overall_roas = total_revenue / total_spend if total_spend > 0 else 0

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("💰 광고비", f"₩{total_spend:,.0f}")
c2.metric("👁 노출수", f"{total_impressions:,.0f}")
c3.metric("🖱 클릭수", f"{total_clicks:,.0f}")
c4.metric("📊 CTR", f"{overall_ctr:.2f}%")
c5.metric("🎯 전환수", f"{total_conversions:,.0f}")
c6.metric("💵 전환 매출액", f"₩{total_revenue:,.0f}")
c7.metric("📈 ROAS", f"{overall_roas:.2f}x")

# ── 채널별 개별 요약 ───────────────────────────────────────────────────────────

st.subheader("채널별 개별 요약")

# 채널별 데이터 수집
_ch_stats = {}
for ch, df in active_data.items():
    spd = df["spend"].sum()
    clk = df["clicks"].sum()
    imp = df["impressions"].sum()
    conv = df["conversions"].sum()
    rev = df["revenue"].sum()
    _ch_stats[ch] = dict(
        spd=spd, clk=clk, imp=imp, conv=conv, rev=rev,
        ctr=(clk / imp * 100) if imp > 0 else 0,
        cpc=spd / clk if clk > 0 else 0,
        roas=rev / spd if spd > 0 else 0,
    )

_chs = list(_ch_stats.keys())

# 헤더 행 (지표명)
_metrics_def = [
    ("💰 광고비",     lambda s: f"₩{s['spd']:,.0f}"),
    ("👁 노출수",     lambda s: f"{s['imp']:,.0f}"),
    ("🖱 클릭수",     lambda s: f"{s['clk']:,.0f}"),
    ("📊 CTR",       lambda s: f"{s['ctr']:.2f}%"),
    ("💡 CPC",       lambda s: f"₩{s['cpc']:,.0f}"),
    ("🎯 전환수",     lambda s: f"{s['conv']:,.0f}"),
    ("💵 전환매출액",  lambda s: f"₩{s['rev']:,.0f}"),
    ("📈 ROAS",      lambda s: f"{s['roas']:.2f}x"),
]

_header_cells = "<th style='text-align:left;padding:12px 16px;font-size:12px;color:#5a6a8a;font-weight:600;border-bottom:1px solid #2a3450;min-width:100px;letter-spacing:0.05em'>채널</th>"
for label, _ in _metrics_def:
    _header_cells += f"<th style='text-align:right;padding:12px 16px;font-size:12px;color:#5a6a8a;font-weight:600;border-bottom:1px solid #2a3450;white-space:nowrap;letter-spacing:0.05em'>{label}</th>"

# 채널 행 데이터
_body_rows = ""
for idx, ch in enumerate(_chs):
    c = CHANNEL_COLORS.get(ch, "#888")
    bg = "rgba(255,255,255,0.03)" if idx % 2 == 0 else "transparent"
    _body_rows += f"<tr style='background:{bg};border-bottom:1px solid #1e2535'>"
    _body_rows += f"<td style='padding:14px 16px;font-weight:700;font-size:15px;color:{c};white-space:nowrap;border-left:4px solid {c}'>{ch}</td>"
    for _, fn in _metrics_def:
        _body_rows += f"<td style='text-align:right;padding:14px 16px;font-weight:600;font-size:14px;color:#d0deff;'>{fn(_ch_stats[ch])}</td>"
    _body_rows += "</tr>"

st.markdown(f"""
<div style='overflow-x:auto;border:1px solid #2a3450;border-radius:12px;background:#161b27;'>
<table style='width:100%;border-collapse:collapse;'>
  <thead><tr>{_header_cells}</tr></thead>
  <tbody>{_body_rows}</tbody>
</table>
</div>
""", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

st.divider()

# ── Channel Comparison ────────────────────────────────────────────────────────

st.subheader("채널별 성과 비교")

channel_agg = (
    combined.groupby("channel")
    .agg(impressions=("impressions", "sum"),
         clicks=("clicks", "sum"),
         spend=("spend", "sum"),
         conversions=("conversions", "sum"),
         revenue=("revenue", "sum"))
    .reset_index()
)
channel_agg["ctr"] = channel_agg["clicks"] / channel_agg["impressions"].replace(0, 1) * 100
channel_agg["roas"] = channel_agg["revenue"] / channel_agg["spend"].replace(0, 1)

DARK_LAYOUT = dict(
    plot_bgcolor="#161b27",
    paper_bgcolor="#161b27",
    font_color="#c0d0f0",
    title_font_size=14,
    title_font_color="#c8d8ff",
    xaxis=dict(gridcolor="#1e2535", linecolor="#2a3450", tickcolor="#2a3450"),
    yaxis=dict(gridcolor="#1e2535", linecolor="#2a3450", tickcolor="#2a3450"),
    legend=dict(bgcolor="#161b27", bordercolor="#2a3450"),
)

def bar_chart(df, y, title, fmt="{:,.0f}", prefix="", suffix=""):
    labels = df[y].apply(lambda v: f"{prefix}{fmt.format(v)}{suffix}")
    fig = px.bar(
        df, x="channel", y=y, color="channel",
        color_discrete_map=CHANNEL_COLORS,
        title=title,
        text=labels,
    )
    fig.update_layout(**DARK_LAYOUT, showlegend=False, height=380)
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_yaxes(showgrid=True)
    return fig

tabs = st.tabs(["💰 광고비", "👁 노출수", "🖱 클릭수", "📊 CTR", "🎯 전환수", "💵 전환 매출액", "📈 ROAS"])
with tabs[0]:
    st.plotly_chart(bar_chart(channel_agg, "spend", "채널별 광고비", "{:,.0f}", "₩"), use_container_width=True)
with tabs[1]:
    st.plotly_chart(bar_chart(channel_agg, "impressions", "채널별 노출수", "{:,.0f}"), use_container_width=True)
with tabs[2]:
    st.plotly_chart(bar_chart(channel_agg, "clicks", "채널별 클릭수", "{:,.0f}"), use_container_width=True)
with tabs[3]:
    st.plotly_chart(bar_chart(channel_agg, "ctr", "채널별 CTR", "{:.2f}", suffix="%"), use_container_width=True)
with tabs[4]:
    st.plotly_chart(bar_chart(channel_agg, "conversions", "채널별 전환수", "{:,.0f}"), use_container_width=True)
with tabs[5]:
    st.plotly_chart(bar_chart(channel_agg, "revenue", "채널별 전환 매출액", "{:,.0f}", "₩"), use_container_width=True)
with tabs[6]:
    st.plotly_chart(bar_chart(channel_agg, "roas", "채널별 ROAS", "{:.2f}", suffix="x"), use_container_width=True)

st.divider()

# ── Daily / Weekly Trend ──────────────────────────────────────────────────────

st.subheader("트렌드 분석")

METRIC_MAP = {
    "광고비 (₩)": "spend",
    "노출수": "impressions",
    "클릭수": "clicks",
    "전환수": "conversions",
    "CTR (%)": "ctr",
}

if "trend_metric" not in st.session_state:
    st.session_state.trend_metric = list(METRIC_MAP.keys())[0]

_trend_left, _trend_right = st.columns([4, 1])
with _trend_left:
    _metric_cols = st.columns(len(METRIC_MAP))
    for _i, _lbl in enumerate(METRIC_MAP.keys()):
        with _metric_cols[_i]:
            if st.button(_lbl, key=f"trend_m_{_i}", use_container_width=True,
                         type="primary" if st.session_state.trend_metric == _lbl else "secondary"):
                st.session_state.trend_metric = _lbl
                st.rerun()
with _trend_right:
    view_unit = st.radio("집계 단위", ["일별", "주별"], horizontal=True)

selected_label = st.session_state.trend_metric

y_col = METRIC_MAP[selected_label]

combined["date_dt"] = pd.to_datetime(combined["date"])

if view_unit == "일별":
    trend = (
        combined.groupby(["date", "channel"])
        .agg({y_col: "sum"})
        .reset_index()
        .sort_values("date")
    )
    x_col = "date"
    title_suffix = "일별"
else:
    combined["week_start"] = combined["date_dt"].dt.to_period("W").apply(lambda r: str(r.start_time.date()))
    trend = (
        combined.groupby(["week_start", "channel"])
        .agg({y_col: "sum"})
        .reset_index()
        .sort_values("week_start")
    )
    x_col = "week_start"
    title_suffix = "주별"

fig_trend = px.line(
    trend, x=x_col, y=y_col, color="channel",
    color_discrete_map=CHANNEL_COLORS,
    title=f"{title_suffix} {selected_label} 추이",
    markers=True,
)
fig_trend.update_layout(
    **DARK_LAYOUT,
    height=420, legend_title_text="채널",
    hovermode="x unified",
)
fig_trend.update_traces(line_width=2.5)
fig_trend.update_xaxes(showgrid=False)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── Budget Forecast ────────────────────────────────────────────────────────────

st.subheader("📈 예산 예측 분석")

days_in_period = max((end_date - start_date).days, 1)

# 채널별 효율 지표 계산
forecast_data = []
for ch, df in active_data.items():
    spd = df["spend"].sum()
    clk = df["clicks"].sum()
    imp = df["impressions"].sum()
    conv = df["conversions"].sum()
    rev = df["revenue"].sum()
    if spd > 0:
        forecast_data.append({
            "channel": ch,
            "spend": spd,
            "daily_spend": spd / days_in_period,
            "cpc": spd / clk if clk > 0 else 0,
            "cpm": spd / imp * 1000 if imp > 0 else 0,
            "conv_rate": conv / clk if clk > 0 else 0,
            "roas": rev / spd,
        })

if forecast_data:
    col_f1, col_f2 = st.columns([1, 2])

    with col_f1:
        st.markdown("**채널별 효율 지표**")
        eff_df = pd.DataFrame(forecast_data)[["channel", "daily_spend", "cpc", "cpm", "conv_rate", "roas"]]
        eff_df.columns = ["채널", "일평균광고비(₩)", "CPC(₩)", "CPM(₩)", "전환율(%)", "ROAS"]
        eff_df["일평균광고비(₩)"] = eff_df["일평균광고비(₩)"].apply(lambda x: f"₩{x:,.0f}")
        eff_df["CPC(₩)"] = eff_df["CPC(₩)"].apply(lambda x: f"₩{x:,.0f}")
        eff_df["CPM(₩)"] = eff_df["CPM(₩)"].apply(lambda x: f"₩{x:,.0f}")
        eff_df["전환율(%)"] = eff_df["전환율(%)"].apply(lambda x: f"{x*100:.2f}%")
        eff_df["ROAS"] = eff_df["ROAS"].apply(lambda x: f"{x:.2f}x")
        st.dataframe(eff_df, hide_index=True, use_container_width=True)

    with col_f2:
        st.markdown("**추가 예산 투입 시 예상 성과**")

        max_budget = max(int(total_spend * 2), 10_000_000)
        _sl_col, _in_col = st.columns([3, 1])
        with _sl_col:
            slider_val = st.slider(
                "추가 예산 슬라이더 (₩)",
                min_value=100_000, max_value=max_budget,
                value=1_000_000, step=100_000, format="₩%d",
            )
        with _in_col:
            add_budget = st.number_input(
                "직접 입력 (₩)", min_value=0, max_value=max_budget,
                value=slider_val, step=100_000,
            )

        # 현재 효율 기반 예측
        total_cpc = total_spend / total_clicks if total_clicks > 0 else 0
        total_conv_rate = total_conversions / total_clicks if total_clicks > 0 else 0
        total_roas_val = total_revenue / total_spend if total_spend > 0 else 0

        proj_clicks = int(add_budget / total_cpc) if total_cpc > 0 else 0
        proj_conv = int(proj_clicks * total_conv_rate)
        proj_revenue = add_budget * total_roas_val

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("추가 예산", f"₩{add_budget:,.0f}")
        p2.metric("예상 클릭수", f"{proj_clicks:,.0f}")
        p3.metric("예상 전환수", f"{proj_conv:,.0f}")
        p4.metric("예상 매출액", f"₩{proj_revenue:,.0f}")

        # 현재 기준 30일 예측
        st.markdown("---")
        st.markdown("**현재 페이스 기준 30일 예측**")
        daily_spend = total_spend / days_in_period
        daily_clicks = total_clicks / days_in_period
        daily_conv = total_conversions / days_in_period
        daily_rev = total_revenue / days_in_period

        p5, p6, p7, p8 = st.columns(4)
        p5.metric("30일 예상 광고비", f"₩{daily_spend*30:,.0f}")
        p6.metric("30일 예상 클릭수", f"{daily_clicks*30:,.0f}")
        p7.metric("30일 예상 전환수", f"{daily_conv*30:,.0f}")
        p8.metric("30일 예상 매출액", f"₩{daily_rev*30:,.0f}")

        # 목표 ROAS 기반 예산 시뮬레이션
        st.markdown("---")
        st.markdown("**목표 ROAS 달성 예산 시뮬레이션**")
        _r_col, _rv_col = st.columns(2)
        with _r_col:
            target_roas = st.number_input(
                "목표 ROAS", min_value=0.1, max_value=50.0, value=3.0, step=0.1,
                format="%.1f",
            )
        with _rv_col:
            default_rev_goal = int(max(total_revenue * 2, total_spend * target_roas)) if total_spend > 0 else 10_000_000
            target_revenue_goal = st.number_input(
                "목표 매출액 (₩)", min_value=0, value=default_rev_goal, step=1_000_000,
            )

        if total_roas_val > 0:
            # 현재 ROAS vs 목표 ROAS
            if total_roas_val >= target_roas:
                st.success(f"✅ 현재 ROAS **{total_roas_val:.2f}x**로 목표 **{target_roas:.1f}x**를 이미 달성했습니다!")
            else:
                st.warning(f"⚠️ 현재 ROAS **{total_roas_val:.2f}x** — 목표 **{target_roas:.1f}x** 미달성 (현재 효율 기준 {target_roas/total_roas_val:.1f}배 개선 필요)")

            # 목표 매출액 달성을 위한 필요 예산
            if target_revenue_goal > 0 and target_roas > 0:
                needed_spend = target_revenue_goal / target_roas
                delta = needed_spend - total_spend
                st.markdown(f"""
<div style='background:#1e2535;border:1px solid #2a3450;border-radius:10px;padding:16px 20px;margin-top:8px'>
<div style='color:#8899bb;font-size:12px;margin-bottom:10px'>목표 매출액 <b style='color:#e0e6f0'>₩{target_revenue_goal:,.0f}</b> / 목표 ROAS <b style='color:#e0e6f0'>{target_roas:.1f}x</b> 달성 시나리오</div>
<div style='display:flex;gap:32px;flex-wrap:wrap'>
  <div><div style='color:#8899bb;font-size:11px'>필요 광고 예산</div><div style='color:#4f8ef7;font-size:22px;font-weight:700'>₩{needed_spend:,.0f}</div></div>
  <div><div style='color:#8899bb;font-size:11px'>현재 대비</div><div style='color:{"#f75a5a" if delta > 0 else "#3ddc84"};font-size:22px;font-weight:700'>{"+" if delta > 0 else ""}₩{delta:,.0f}</div></div>
  <div><div style='color:#8899bb;font-size:11px'>현재 광고비</div><div style='color:#c0d0f0;font-size:22px;font-weight:700'>₩{total_spend:,.0f}</div></div>
</div>
</div>
""", unsafe_allow_html=True)
        else:
            st.info("전환 매출 데이터가 없어 ROAS 기반 예측이 어렵습니다. (META·NAVER 전환 추적 연동 필요)")
else:
    st.info("예측 분석을 위한 광고비 데이터가 없습니다.")

st.divider()

# ── Inflow Path (Treemap) ─────────────────────────────────────────────────────

st.subheader("유입경로 분석")

_TREEMAP_METRICS = ["광고비 (₩)", "노출수", "클릭수", "전환수"]
if "treemap_metric" not in st.session_state:
    st.session_state.treemap_metric = _TREEMAP_METRICS[0]

_tm_cols = st.columns(len(_TREEMAP_METRICS))
for _i, _lbl in enumerate(_TREEMAP_METRICS):
    with _tm_cols[_i]:
        if st.button(_lbl, key=f"tm_m_{_i}", use_container_width=True,
                     type="primary" if st.session_state.treemap_metric == _lbl else "secondary"):
            st.session_state.treemap_metric = _lbl
            st.rerun()

treemap_metric_label = st.session_state.treemap_metric
tm_col = METRIC_MAP[treemap_metric_label]

treemap_df = (
    combined.groupby(["channel", "campaign"])
    .agg({tm_col: "sum"})
    .reset_index()
)
treemap_df = treemap_df[treemap_df[tm_col] > 0]

if not treemap_df.empty:
    fig_tree = px.treemap(
        treemap_df,
        path=["channel", "campaign"],
        values=tm_col,
        color="channel",
        color_discrete_map=CHANNEL_COLORS,
        title=f"채널 › 캠페인 ({treemap_metric_label})",
    )
    fig_tree.update_layout(height=500, **{k: v for k, v in DARK_LAYOUT.items() if k in ["plot_bgcolor","paper_bgcolor","font_color","title_font_color"]})
    fig_tree.update_traces(textinfo="label+value+percent parent")
    st.plotly_chart(fig_tree, use_container_width=True)
else:
    st.info("유입경로 데이터가 없습니다.")

st.divider()

# ── Campaign Detail Table ──────────────────────────────────────────────────────

st.subheader("캠페인 상세 현황")

campaign_agg = (
    combined.groupby(["channel", "campaign"])
    .agg(impressions=("impressions", "sum"),
         clicks=("clicks", "sum"),
         spend=("spend", "sum"),
         conversions=("conversions", "sum"),
         revenue=("revenue", "sum"))
    .reset_index()
)
campaign_agg["ctr"] = campaign_agg["clicks"] / campaign_agg["impressions"].replace(0, 1) * 100
campaign_agg["cpc"] = campaign_agg["spend"] / campaign_agg["clicks"].replace(0, 1)
campaign_agg["roas"] = campaign_agg["revenue"] / campaign_agg["spend"].replace(0, 1)
campaign_agg = campaign_agg.sort_values("spend", ascending=False)

display = campaign_agg.copy()
display.columns = ["채널", "캠페인명", "노출수", "클릭수", "광고비(₩)", "전환수", "전환매출액(₩)", "CTR(%)", "CPC(₩)", "ROAS"]
display["노출수"] = display["노출수"].apply(lambda x: f"{x:,.0f}")
display["클릭수"] = display["클릭수"].apply(lambda x: f"{x:,.0f}")
display["광고비(₩)"] = display["광고비(₩)"].apply(lambda x: f"₩{x:,.0f}")
display["전환수"] = display["전환수"].apply(lambda x: f"{x:,.0f}")
display["전환매출액(₩)"] = display["전환매출액(₩)"].apply(lambda x: f"₩{x:,.0f}")
display["CTR(%)"] = display["CTR(%)"].apply(lambda x: f"{x:.2f}%")
display["CPC(₩)"] = display["CPC(₩)"].apply(lambda x: f"₩{x:,.0f}")
display["ROAS"] = display["ROAS"].apply(lambda x: f"{x:.2f}x")

st.dataframe(display, use_container_width=True, hide_index=True, height=400)

# ── Footer ─────────────────────────────────────────────────────────────────────

st.caption(
    f"마지막 조회: {datetime.now().strftime('%Y-%m-%d %H:%M')} KST  |  "
    "데이터 캐시 1시간  |  광고비·전환수는 각 플랫폼 기준  |  예측은 조회기간 평균 효율 기반 추정치"
)
