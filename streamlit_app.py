import random
from datetime import date, timedelta

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="GrowthPilot AI",
    page_icon="📈",
    layout="wide",
)


RECENT_DAYS = 3
BASELINE_DAYS = 7
INSTALL_DROP_THRESHOLD = -0.20
FUNNEL_DROP_THRESHOLD = -0.15


@st.cache_data
def make_sample_data():
    """生成波动较平稳、且包含一个明确异常的演示数据集。"""
    rng = random.Random(42)

    apps = [f"App_{i:02d}" for i in range(1, 21)]
    countries = ["Nigeria", "India", "Philippines", "Indonesia", "Kenya"]
    channels = ["PAI", "Push", "Banner", "开屏", "搜索"]
    today = date.today()
    rows = []

    # 先为每个 App × 国家 × 渠道设置一个稳定的历史基准。
    # 这样最近三天的异常不会被随机波动掩盖。
    profiles = {}
    for app_index, app in enumerate(apps, start=1):
        for country in countries:
            for channel in channels:
                profiles[(app, country, channel)] = {
                    "impressions": rng.randint(900, 1700),
                    "ctr": rng.uniform(0.055, 0.105),
                    "install_rate": rng.uniform(0.22, 0.42),
                    "retention_d1": rng.uniform(0.18, 0.32),
                    "unit_price": round(rng.uniform(0.04, 0.12), 3),
                    "target_factor": 1.03 + app_index * 0.001,
                }

    for day_offset in range(14):
        current_date = today - timedelta(days=13 - day_offset)

        for app in apps:
            for country in countries:
                for channel in channels:
                    profile = profiles[(app, country, channel)]

                    impressions = int(
                        profile["impressions"] * rng.uniform(0.96, 1.04)
                    )
                    ctr = profile["ctr"] * rng.uniform(0.97, 1.03)
                    install_rate = (
                        profile["install_rate"] * rng.uniform(0.97, 1.03)
                    )
                    retention_d1 = min(
                        0.95,
                        max(
                            0.01,
                            profile["retention_d1"] * rng.uniform(0.97, 1.03),
                        ),
                    )

                    # 植入演示异常：菲律宾 Push 最近三天的点击率和安装转化下降。
                    if (
                        country == "Philippines"
                        and channel == "Push"
                        and day_offset >= 11
                    ):
                        ctr *= 0.55
                        install_rate *= 0.82
                        retention_d1 = max(0.01, retention_d1 - 0.04)

                    clicks = int(impressions * ctr)
                    installs = int(clicks * install_rate)
                    unit_price = profile["unit_price"]

                    baseline_installs = (
                        profile["impressions"]
                        * profile["ctr"]
                        * profile["install_rate"]
                    )
                    target_revenue = (
                        baseline_installs
                        * unit_price
                        * profile["target_factor"]
                    )

                    rows.append(
                        {
                            "date": current_date,
                            "app": app,
                            "country": country,
                            "channel": channel,
                            "impressions": impressions,
                            "clicks": clicks,
                            "installs": installs,
                            "retention_d1": retention_d1,
                            "unit_price": unit_price,
                            "target_revenue": target_revenue,
                        }
                    )

    return pd.DataFrame(rows)


def prepare_data(raw_df):
    """检查字段并生成后续分析所需的计算列。"""
    required_columns = [
        "date",
        "app",
        "country",
        "channel",
        "impressions",
        "clicks",
        "installs",
        "retention_d1",
        "unit_price",
        "target_revenue",
    ]

    missing_columns = [
        column for column in required_columns if column not in raw_df.columns
    ]
    if missing_columns:
        return None, missing_columns

    df = raw_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    for column in ["app", "country", "channel"]:
        df[column] = df[column].astype(str)

    numeric_columns = [
        "impressions",
        "clicks",
        "installs",
        "retention_d1",
        "unit_price",
        "target_revenue",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df["revenue"] = df["installs"] * df["unit_price"]
    df["retention_users"] = df["retention_d1"] * df["installs"]
    return df, []


def summarize_period(period_df, group_columns):
    """把一个时间段汇总为日均规模指标和整体转化率。"""
    if period_df.empty:
        return pd.DataFrame()

    day_count = max(period_df["date"].nunique(), 1)
    grouped = (
        period_df.groupby(group_columns, as_index=False, dropna=False)
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            installs=("installs", "sum"),
            retention_users=("retention_users", "sum"),
        )
    )

    grouped["impressions_daily"] = grouped["impressions"] / day_count
    grouped["clicks_daily"] = grouped["clicks"] / day_count
    grouped["installs_daily"] = grouped["installs"] / day_count
    grouped["ctr"] = grouped["clicks"] / grouped["impressions"].replace(0, pd.NA)
    grouped["install_rate"] = grouped["installs"] / grouped["clicks"].replace(0, pd.NA)
    grouped["retention_d1"] = (
        grouped["retention_users"] / grouped["installs"].replace(0, pd.NA)
    )

    return grouped[
        group_columns
        + [
            "impressions_daily",
            "clicks_daily",
            "installs_daily",
            "ctr",
            "install_rate",
            "retention_d1",
        ]
    ].fillna(0)


def compare_periods(df, group_columns):
    """比较最近3天和此前7天，输出各维度的变化。"""
    max_date = df["date"].max()
    recent_start = max_date - pd.Timedelta(days=RECENT_DAYS - 1)
    baseline_start = recent_start - pd.Timedelta(days=BASELINE_DAYS)

    recent = df[df["date"] >= recent_start]
    baseline = df[
        (df["date"] >= baseline_start) & (df["date"] < recent_start)
    ]

    recent_summary = summarize_period(recent, group_columns)
    baseline_summary = summarize_period(baseline, group_columns)

    if recent_summary.empty or baseline_summary.empty:
        return pd.DataFrame(), recent_start, baseline_start

    comparison = baseline_summary.merge(
        recent_summary,
        on=group_columns,
        how="inner",
        suffixes=("_baseline", "_recent"),
    )

    change_metrics = [
        "impressions_daily",
        "clicks_daily",
        "installs_daily",
        "ctr",
        "install_rate",
    ]
    for metric in change_metrics:
        baseline_values = comparison[f"{metric}_baseline"].replace(0, pd.NA)
        comparison[f"{metric}_change"] = (
            comparison[f"{metric}_recent"] / baseline_values - 1
        ).fillna(0)

    comparison["retention_change_pp"] = (
        comparison["retention_d1_recent"]
        - comparison["retention_d1_baseline"]
    )
    comparison["install_drop"] = (
        comparison["installs_daily_baseline"]
        - comparison["installs_daily_recent"]
    ).clip(lower=0)

    return comparison, recent_start, baseline_start


def diagnose_stage(row):
    """按照漏斗从上到下判断最先出现明显下降的环节。"""
    if row["impressions_daily_change"] <= FUNNEL_DROP_THRESHOLD:
        return "触达/曝光下降"
    if row["ctr_change"] <= FUNNEL_DROP_THRESHOLD:
        return "点击率下降"
    if row["install_rate_change"] <= FUNNEL_DROP_THRESHOLD:
        return "点击→安装转化下降"
    if row["retention_change_pp"] <= -0.03:
        return "次留下降"
    return "安装量下降，需继续拆解"


def detect_anomalies(df):
    comparison, recent_start, baseline_start = compare_periods(
        df, ["app", "country", "channel"]
    )
    if comparison.empty:
        return comparison, recent_start, baseline_start

    anomalies = comparison[
        comparison["installs_daily_change"] <= INSTALL_DROP_THRESHOLD
    ].copy()
    anomalies["suspected_stage"] = anomalies.apply(diagnose_stage, axis=1)
    anomalies = anomalies.sort_values(
        ["install_drop", "installs_daily_change"],
        ascending=[False, True],
    )
    return anomalies, recent_start, baseline_start


def format_percent(value):
    return f"{value:+.1%}"


st.title("📈 GrowthPilot AI")
st.subheader("海外 App 商业化运营诊断助手")
st.write(
    "上传归因数据后，系统将帮助运营人员完成经营监控、"
    "异常预警、三级归因和策略建议。"
)

uploaded_file = st.file_uploader(
    "上传归因数据 CSV（不上传时使用模拟数据）",
    type=["csv"],
)

if uploaded_file is not None:
    raw_df = pd.read_csv(uploaded_file)
    data_source = "你上传的数据"
else:
    raw_df = make_sample_data()
    data_source = "系统生成的模拟数据"

df, missing_columns = prepare_data(raw_df)
if missing_columns:
    st.error(f"CSV 缺少这些字段：{missing_columns}")
    st.stop()
if df.empty:
    st.error("没有可分析的数据，请检查日期和字段内容。")
    st.stop()

st.sidebar.header("筛选条件")
app_options = ["全部"] + sorted(df["app"].unique().tolist())
country_options = ["全部"] + sorted(df["country"].unique().tolist())
channel_options = ["全部"] + sorted(df["channel"].unique().tolist())

selected_app = st.sidebar.selectbox("App", app_options)
selected_country = st.sidebar.selectbox("国家", country_options)
selected_channel = st.sidebar.selectbox("渠道", channel_options)

filtered = df.copy()
if selected_app != "全部":
    filtered = filtered[filtered["app"] == selected_app]
if selected_country != "全部":
    filtered = filtered[filtered["country"] == selected_country]
if selected_channel != "全部":
    filtered = filtered[filtered["channel"] == selected_channel]

if filtered.empty:
    st.warning("当前筛选条件没有数据，请更换筛选条件。")
    st.stop()

total_installs = int(filtered["installs"].sum())
total_revenue = filtered["revenue"].sum()
total_target = filtered["target_revenue"].sum()
retention_rate = (
    filtered["retention_users"].sum() / total_installs
    if total_installs > 0
    else 0
)
completion_rate = total_revenue / total_target if total_target > 0 else 0

st.caption(
    f"数据来源：{data_source}｜"
    f"数据范围：{filtered['date'].min().date()} 至 "
    f"{filtered['date'].max().date()}"
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("安装量", f"{total_installs:,}")
col2.metric("次留率", f"{retention_rate:.1%}")
col3.metric("预估营收", f"${total_revenue:,.2f}")
col4.metric("目标完成率", f"{completion_rate:.1%}")

st.divider()
st.subheader("近 14 日趋势")
trend = (
    filtered.groupby("date", as_index=True)
    .agg(安装量=("installs", "sum"), 预估营收=("revenue", "sum"))
)
st.line_chart(trend)

st.subheader("国家 × 渠道经营表现")
summary = (
    filtered.groupby(["country", "channel"], as_index=False)
    .agg(
        点击量=("clicks", "sum"),
        安装量=("installs", "sum"),
        预估营收=("revenue", "sum"),
        次留人数=("retention_users", "sum"),
    )
)
summary["次留率"] = summary["次留人数"] / summary["安装量"].replace(0, pd.NA)
summary = summary.drop(columns=["次留人数"])
summary["次留率"] = summary["次留率"].fillna(0).map(lambda value: f"{value:.1%}")
summary["预估营收"] = summary["预估营收"].map(lambda value: f"${value:,.2f}")
st.dataframe(summary, width="stretch", hide_index=True)

st.divider()
st.header("🚨 异常自动检测")
st.caption(
    "规则：最近3日日均安装量较此前7日日均下降20%以上时触发；"
    "系统再根据触达/曝光、点击率和点击→安装转化率定位漏斗环节。"
)

anomalies, recent_start, baseline_start = detect_anomalies(filtered)

if anomalies.empty:
    st.success("当前筛选范围内未发现达到阈值的安装异常。")
else:
    st.warning(f"发现 {len(anomalies)} 个 App × 国家 × 渠道异常组合。")

    anomaly_display = anomalies[
        [
            "app",
            "country",
            "channel",
            "installs_daily_baseline",
            "installs_daily_recent",
            "installs_daily_change",
            "ctr_change",
            "install_rate_change",
            "suspected_stage",
        ]
    ].copy()
    anomaly_display.columns = [
        "App",
        "国家",
        "渠道",
        "此前7日日均安装",
        "最近3日日均安装",
        "安装变化",
        "CTR变化",
        "安装转化变化",
        "初步定位",
    ]
    anomaly_display["此前7日日均安装"] = anomaly_display[
        "此前7日日均安装"
    ].round(1)
    anomaly_display["最近3日日均安装"] = anomaly_display[
        "最近3日日均安装"
    ].round(1)
    for column in ["安装变化", "CTR变化", "安装转化变化"]:
        anomaly_display[column] = anomaly_display[column].map(format_percent)

    st.dataframe(anomaly_display.head(30), width="stretch", hide_index=True)

    st.subheader("三级归因详情")
    anomaly_keys = list(
        anomalies[["app", "country", "channel"]]
        .itertuples(index=False, name=None)
    )
    chosen_key = st.selectbox(
        "选择一个异常继续拆解",
        anomaly_keys,
        format_func=lambda item: f"{item[0]}｜{item[1]}｜{item[2]}",
    )
    chosen_app, chosen_country, chosen_channel = chosen_key

    st.markdown("#### 第一级：国家")
    country_comparison, _, _ = compare_periods(
        filtered[filtered["app"] == chosen_app],
        ["country"],
    )
    country_comparison = country_comparison.sort_values(
        "install_drop", ascending=False
    )
    country_display = country_comparison[
        [
            "country",
            "installs_daily_baseline",
            "installs_daily_recent",
            "installs_daily_change",
            "install_drop",
        ]
    ].copy()
    country_display.columns = [
        "国家",
        "此前7日日均安装",
        "最近3日日均安装",
        "安装变化",
        "日均掉量贡献",
    ]
    country_display["此前7日日均安装"] = country_display[
        "此前7日日均安装"
    ].round(1)
    country_display["最近3日日均安装"] = country_display[
        "最近3日日均安装"
    ].round(1)
    country_display["安装变化"] = country_display["安装变化"].map(format_percent)
    country_display["日均掉量贡献"] = country_display["日均掉量贡献"].round(1)
    st.dataframe(country_display, width="stretch", hide_index=True)

    st.markdown("#### 第二级：渠道")
    channel_scope = filtered[
        (filtered["app"] == chosen_app)
        & (filtered["country"] == chosen_country)
    ]
    channel_comparison, _, _ = compare_periods(channel_scope, ["channel"])
    channel_comparison = channel_comparison.sort_values(
        "install_drop", ascending=False
    )
    channel_display = channel_comparison[
        [
            "channel",
            "installs_daily_baseline",
            "installs_daily_recent",
            "installs_daily_change",
            "install_drop",
        ]
    ].copy()
    channel_display.columns = [
        "渠道",
        "此前7日日均安装",
        "最近3日日均安装",
        "安装变化",
        "日均掉量贡献",
    ]
    channel_display["此前7日日均安装"] = channel_display[
        "此前7日日均安装"
    ].round(1)
    channel_display["最近3日日均安装"] = channel_display[
        "最近3日日均安装"
    ].round(1)
    channel_display["安装变化"] = channel_display["安装变化"].map(format_percent)
    channel_display["日均掉量贡献"] = channel_display["日均掉量贡献"].round(1)
    st.dataframe(channel_display, width="stretch", hide_index=True)

    st.markdown("#### 第三级：漏斗")
    chosen_row = anomalies[
        (anomalies["app"] == chosen_app)
        & (anomalies["country"] == chosen_country)
        & (anomalies["channel"] == chosen_channel)
    ].iloc[0]

    funnel1, funnel2, funnel3, funnel4 = st.columns(4)
    funnel1.metric(
        "日均触达/曝光",
        f"{chosen_row['impressions_daily_recent']:,.0f}",
        format_percent(chosen_row["impressions_daily_change"]),
    )
    funnel2.metric(
        "点击率 CTR",
        f"{chosen_row['ctr_recent']:.1%}",
        format_percent(chosen_row["ctr_change"]),
    )
    funnel3.metric(
        "点击→安装转化率",
        f"{chosen_row['install_rate_recent']:.1%}",
        format_percent(chosen_row["install_rate_change"]),
    )
    funnel4.metric(
        "次留率",
        f"{chosen_row['retention_d1_recent']:.1%}",
        f"{chosen_row['retention_change_pp'] * 100:+.1f} 个百分点",
    )

    st.info(
        f"初步结论：{chosen_app} 在 {chosen_country} 的 "
        f"{chosen_channel} 渠道最近3日日均安装较此前7日变化 "
        f"{format_percent(chosen_row['installs_daily_change'])}；"
        f"异常优先定位为“{chosen_row['suspected_stage']}”。"
    )

st.download_button(
    "下载模拟归因数据",
    data=make_sample_data().to_csv(index=False).encode("utf-8-sig"),
    file_name="sample_attribution_data.csv",
    mime="text/csv",
)
