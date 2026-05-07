import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

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
[data-testid="metric-container"] {
    background: #f8faff;
    border: 1px solid #e0e7ff;
    border-radius: 10px;
    padding: 16px;
}
.channel-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 600;
}
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

def bar_chart(df, y, title, fmt="{:,.0f}", prefix="", suffix=""):
    labels = df[y].apply(lambda v: f"{prefix}{fmt.format(v)}{suffix}")
    fig = px.bar(
        df, x="channel", y=y, color="channel",
        color_discrete_map=CHANNEL_COLORS,
        title=title,
        text=labels,
    )
    fig.update_layout(showlegend=False, height=380, title_font_size=14,
                      plot_bgcolor="white", paper_bgcolor="white")
    fig.update_traces(textposition="outside", marker_line_width=0)
    fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
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

# ── Daily Trend ───────────────────────────────────────────────────────────────

st.subheader("일별 트렌드")

METRIC_MAP = {
    "광고비 (₩)": "spend",
    "노출수": "impressions",
    "클릭수": "clicks",
    "전환수": "conversions",
    "CTR (%)": "ctr",
}

col_left, col_right = st.columns([3, 1])
with col_right:
    selected_label = st.selectbox("지표", list(METRIC_MAP.keys()))
y_col = METRIC_MAP[selected_label]

daily = (
    combined.groupby(["date", "channel"])
    .agg({y_col: "sum"})
    .reset_index()
    .sort_values("date")
)

fig_trend = px.line(
    daily, x="date", y=y_col, color="channel",
    color_discrete_map=CHANNEL_COLORS,
    title=f"일별 {selected_label} 추이",
    markers=True,
)
fig_trend.update_layout(
    height=420, legend_title_text="채널",
    plot_bgcolor="white", paper_bgcolor="white",
    hovermode="x unified",
)
fig_trend.update_yaxes(showgrid=True, gridcolor="#f0f0f0")
fig_trend.update_xaxes(showgrid=False)
st.plotly_chart(fig_trend, use_container_width=True)

st.divider()

# ── Inflow Path (Treemap) ─────────────────────────────────────────────────────

st.subheader("유입경로 분석")

treemap_metric_label = st.selectbox(
    "기준 지표",
    ["광고비 (₩)", "노출수", "클릭수", "전환수"],
    key="treemap_metric",
)
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
    fig_tree.update_layout(height=500)
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
campaign_agg["roas"] = campaign_agg["revenue"] / campaign_agg["spend"].replace(0, 1)
campaign_agg = campaign_agg.sort_values("spend", ascending=False)

display = campaign_agg.copy()
display.columns = ["채널", "캠페인명", "노출수", "클릭수", "광고비(₩)", "전환수", "전환매출액(₩)", "CTR(%)", "ROAS"]
display["노출수"] = display["노출수"].apply(lambda x: f"{x:,.0f}")
display["클릭수"] = display["클릭수"].apply(lambda x: f"{x:,.0f}")
display["광고비(₩)"] = display["광고비(₩)"].apply(lambda x: f"₩{x:,.0f}")
display["전환수"] = display["전환수"].apply(lambda x: f"{x:,.0f}")
display["전환매출액(₩)"] = display["전환매출액(₩)"].apply(lambda x: f"₩{x:,.0f}")
display["CTR(%)"] = display["CTR(%)"].apply(lambda x: f"{x:.2f}%")
display["ROAS"] = display["ROAS"].apply(lambda x: f"{x:.2f}x")

st.dataframe(display, use_container_width=True, hide_index=True, height=400)

# ── Footer ─────────────────────────────────────────────────────────────────────

st.caption(
    f"마지막 조회: {datetime.now().strftime('%Y-%m-%d %H:%M')} KST  |  "
    "데이터 캐시 1시간  |  광고비·전환수는 각 플랫폼 기준"
)
