import streamlit as st

st.set_page_config(
    page_title="GrowthPilot AI",
    page_icon="📈",
    layout="wide"
)

st.title("📈 GrowthPilot AI")
st.subheader("海外 App 商业化运营诊断助手")

st.info(
    "上传归因数据后，系统将帮助运营人员完成经营监控、"
    "异常预警、三级归因和策略建议。"
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("管理 App", "20款")

with col2:
    st.metric("覆盖市场", "5个")

with col3:
    st.metric("分发渠道", "5类")

with col4:
    st.metric("今日异常", "待检测")

st.divider()

st.subheader("目前正在建设的功能")

st.write("✅ 经营指标看板")
st.write("⏳ 异常自动预警")
st.write("⏳ 国家—渠道—漏斗三级归因")
st.write("⏳ AI运营策略建议")

st.success("项目已经成功运行！")
