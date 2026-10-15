import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import cloudinary
import cloudinary.uploader
from datetime import datetime
import uuid

# 페이지 기본 설정
st.set_page_config(page_title="시설보수 관리 시스템", page_icon="🔧", layout="wide")

# ---------------------------------------------------------
# 1. 외부 서비스 연결 (Cloudinary & Google Sheets)
# ---------------------------------------------------------
# Cloudinary 설정
cloudinary.config(
    cloud_name=st.secrets["cloudinary"]["cloud_name"],
    api_key=st.secrets["cloudinary"]["api_key"],
    api_secret=st.secrets["cloudinary"]["api_secret"]
)

# 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    """구글 시트 데이터 읽기 (캐시 0초 설정으로 실시간 반영)"""
    return conn.read(ttl=0)

# ---------------------------------------------------------
# 2. 메인 UI 및 탭 구성
# ---------------------------------------------------------
st.title("🛠️ 시설보수 요청 및 통합 관리 시스템")

tab1, tab2, tab3 = st.tabs(["📱 보수 요청 (접수)", "📋 담당자 조치 관리", "📊 개선 결과 통계"])

# =========================================================
# TAB 1: 모바일 QR 접수 페이지
# =========================================================
with tab1:
    st.subheader("시설물 고장/보수 요청")
    
    # URL 파라미터에서 facility_id 가져오기 (예: ?facility_id=A_101)
    query_params = st.query_params
    default_facility = query_params.get("facility_id", "미지정_직접입력")

    with st.form("repair_form", clear_on_submit=True):
        facility_id = st.text_input("📍 시설/위치 ID", value=default_facility)
        requester = st.text_input("👤 요청자 이름/연락처", placeholder="예: 홍길동 (010-1234-5678)")
        category = st.selectbox("🏷️ 고장 유형", ["전기/조명", "수도/누수", "냉난방", "문/창호", "가구/집기", "기타"])
        description = st.text_area("📝 고장 내용 상세", placeholder="고장 증상을 자세히 적어주세요.")
        uploaded_file = st.file_uploader("📷 현장 사진 첨부", type=["jpg", "jpeg", "png"])

        submitted = st.form_submit_button("🚨 보수 요청 제출하기")

        if submitted:
            if not requester or not description:
                st.error("요청자 정보와 고장 내용을 입력해 주세요.")
            else:
                with st.spinner("접수 처리 중입니다..."):
                    # 1. 사진 Cloudinary 업로드
                    image_url = ""
                    if uploaded_file is not None:
                        upload_result = cloudinary.uploader.upload(uploaded_file)
                        image_url = upload_result.get("secure_url", "")

                    # 2. 새로운 데이터 행 생성
                    new_id = str(uuid.uuid4())[:8]
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    new_data = pd.DataFrame([{
                        "ID": new_id,
                        "접수일시": now_str,
                        "시설ID": facility_id,
                        "요청자": requester,
                        "카테고리": category,
                        "고장내용": description,
                        "사진URL": image_url,
                        "처리상태": "접수중",
                        "조치일시": "",
                        "조치내용": ""
                    }])

                    # 3. 구글 시트 업데이트
                    existing_df = load_data()
                    updated_df = pd.concat([existing_df, new_data], ignore_index=True)
                    conn.update(data=updated_df)

                    st.success("✅ 보수 요청이 성공적으로 접수되었습니다!")
                    st.balloons()

# =========================================================
# TAB 2: 담당자 확인 및 조치 등록 페이지
# =========================================================
with tab2:
    st.subheader("📋 접수 내역 확인 및 조치 완료 처리")
    
    df = load_data()
    
    if df.empty or "처리상태" not in df.columns:
        st.info("현재 접수된 내역이 없습니다.")
    else:
        # 필터링 옵션
        status_filter = st.radio("상태 필터", ["전체", "접수중", "조치완료"], horizontal=True)
        
        filtered_df = df if status_filter == "전체" else df[df["처리상태"] == status_filter]
        
        st.dataframe(filtered_df[["ID", "접수일시", "시설ID", "카테고리", "고장내용", "처리상태", "조치일시"]], use_container_width=True)

        st.markdown("---")
        st.subheader("🛠️ 조치 결과 입력")

        # '접수중'인 건들의 ID 목록
        pending_items = df[df["처리상태"] == "접수중"]
        
        if pending_items.empty:
            st.success("🎉 현재 미처리된 보수 요청이 없습니다!")
        else:
            selected_id = st.selectbox("조치할 요청건 선택 (ID 기준)", pending_items["ID"].tolist())
            
            # 선택한 건의 상세정보 표시
            selected_row = df[df["ID"] == selected_id].iloc[0]
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**위치:** {selected_row['시설ID']}")
                st.write(f"**요청자:** {selected_row['요청자']}")
                st.write(f"**고장내용:** {selected_row['고장내용']}")
            with col2:
                if selected_row['사진URL']:
                    st.image(selected_row['사진URL'], caption="접수 현장 사진", width=250)

            with st.form("action_form"):
                action_text = st.text_area("조치 내용 및 개선 결과 입력")
                complete_btn = st.form_submit_button("✅ 조치 완료 처리")

                if complete_btn:
                    if not action_text:
                        st.error("조치 내용을 입력해 주세요.")
                    else:
                        # 데이터 수정
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df.loc[df["ID"] == selected_id, "처리상태"] = "조치완료"
                        df.loc[df["ID"] == selected_id, "조치일시"] = now_str
                        df.loc[df["ID"] == selected_id, "조치내용"] = action_text

                        conn.update(data=df)
                        st.success(f"ID {selected_id} 건이 '조치완료' 처리되었습니다.")
                        st.rerun()

# =========================================================
# TAB 3: 개선 결과 및 현황 통계 대시보드
# =========================================================
with tab3:
    st.subheader("📊 시설 보수 현황 통계")
    
    df = load_data()

    if not df.empty and "처리상태" in df.columns:
        # 요약 지표 (KPI)
        total_cnt = len(df)
        pending_cnt = len(df[df["처리상태"] == "접수중"])
        completed_cnt = len(df[df["처리상태"] == "조치완료"])
        complete_rate = (completed_cnt / total_cnt * 100) if total_cnt > 0 else 0

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("총 접수 건수", f"{total_cnt} 건")
        kpi2.metric("처리 대기", f"{pending_cnt} 건", delta_color="inverse")
        kpi3.metric("조치 완료", f"{completed_cnt} 건")
        kpi4.metric("조치 완료율", f"{complete_rate:.1f} %")

        st.markdown("---")

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.markdown("##### 🏷️ 카테고리별 고장 발생 비율")
            cat_counts = df["카테고리"].value_counts().reset_index()
            cat_counts.columns = ["카테고리", "건수"]
            fig_pie = px.pie(cat_counts, values="건수", names="카테고리", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_chart2:
            st.markdown("##### 📍 시설/위치별 보수 요청 Top 5")
            fac_counts = df["시설ID"].value_counts().head(5).reset_index()
            fac_counts.columns = ["시설ID", "건수"]
            fig_bar = px.bar(fac_counts, x="시설ID", y="건수", color="건수", color_continuous_scale="Reds")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("통계를 표시할 데이터가 부족합니다.")