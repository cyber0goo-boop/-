import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import cloudinary
import cloudinary.uploader

# ---------------------------------------------------------
# 1. 페이지 및 기본 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="시설보수 요청 및 통합 관리 시스템",
    page_icon="🛠️",
    layout="wide"
)

# 필수 컬럼 정의
REQUIRED_COLUMNS = [
    "접수일시", "시설ID", "요청자", "고장유형", 
    "고장내용", "사진URL", "처리상태", "조치내용", "조치일시"
]

# Cloudinary 설정
if "cloudinary" in st.secrets:
    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"]
    )

# Google Sheets 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 불러오기 (KeyError 방지 자동 보정 포함)
def load_data():
    try:
        df = conn.read(ttl=0)
        if df.empty:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
        
        # 구글 시트에 누락된 필수 열이 있다면 자동으로 empty 값으로 추가
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                df[col] = ""
                
        return df[REQUIRED_COLUMNS]  # 열 순서 표준화
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

# 엑셀 파일 생성 함수 (다중 시트 구성)
def create_excel_report(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 시트 1: 전체 접수 내역
        df.to_excel(writer, sheet_name='전체_접수내역', index=False)
        
        # 시트 2: 고장 유형별 통계
        type_df = df["고장유형"].value_counts().reset_index()
        type_df.columns = ["고장유형", "접수건수"]
        type_df.to_excel(writer, sheet_name='고장유형별_통계', index=False)
        
        # 시트 3: 처리 상태별 통계
        status_df = df["처리상태"].value_counts().reset_index()
        status_df.columns = ["처리상태", "접수건수"]
        status_df.to_excel(writer, sheet_name='처리상태별_통계', index=False)

    return output.getvalue()

# 관리자 인증
def check_password(key_prefix="admin"):
    if "admin_logged_in" not in st.session_state:
        st.session_state["admin_logged_in"] = False

    if not st.session_state["admin_logged_in"]:
        st.info("🔒 담당자 전용 기능입니다. 비밀번호를 입력해 주세요.")
        pwd_input = st.text_input("🔑 관리자 비밀번호", type="password", key=f"{key_prefix}_pwd")
        if st.button("인증하기", key=f"{key_prefix}_btn"):
            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "")
            if pwd_input == admin_pwd:
                st.session_state["admin_logged_in"] = True
                st.success("🔓 관리자 인증이 완료되었습니다.")
                st.rerun()
            else:
                st.error("❌ 비밀번호가 올바르지 않습니다.")
        return False
    return True


# ---------------------------------------------------------
# 2. 메인 UI 화면 구성
# ---------------------------------------------------------
st.title("🛠️ 시설보수 요청 및 통합 관리 시스템")

tab1, tab2, tab3 = st.tabs([
    "📱 보수 요청 (접수)", 
    "📋 담당자 조치 관리", 
    "📊 개선 결과 통계"
])


# =========================================================
# TAB 1: 보수 요청 (접수)
# =========================================================
with tab1:
    st.subheader("📍 시설물 고장/보수 요청")

    query_params = st.query_params
    default_facility = query_params.get("facility_id", "미지정_직접입력")

    with st.form("repair_request_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            facility_id = st.text_input("📍 시설/위치 ID", value=default_facility)
            requester_info = st.text_input("👤 요청자 이름/연락처", placeholder="예: 홍길동 (010-1234-5678)")
        
        with col2:
            issue_type = st.selectbox("🏷️ 고장 유형", ["전기/조명", "수도/배관", "냉난방", "건축/시설물", "기타"])
            uploaded_file = st.file_uploader("📷 현장 사진 첨부", type=["jpg", "jpeg", "png"])

        issue_detail = st.text_area("📝 고장 내용 상세", placeholder="고장 증상을 자세히 적어주세요.")
        
        submitted = st.form_submit_button("🚨 보수 요청 제출하기", use_container_width=True)

    if submitted:
        if not requester_info or not issue_detail:
            st.warning("⚠️ 요청자 정보와 고장 내용을 입력해 주세요.")
        else:
            photo_url = "없음"
            if uploaded_file is not None:
                with st.spinner("사진을 업로드 중입니다..."):
                    upload_result = cloudinary.uploader.upload(uploaded_file)
                    photo_url = upload_result.get("secure_url", "없음")

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = {
                "접수일시": now_str,
                "시설ID": facility_id,
                "요청자": requester_info,
                "고장유형": issue_type,
                "고장내용": issue_detail,
                "사진URL": photo_url,
                "처리상태": "접수완료",
                "조치내용": "",
                "조치일시": ""
            }

            df = load_data()
            updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            conn.update(data=updated_df)

            st.balloons()
            st.success("✅ 성공적으로 보수 요청이 접수되었습니다!")


# =========================================================
# TAB 2: 담당자 조치 관리
# =========================================================
with tab2:
    if check_password(key_prefix="tab2"):
        st.subheader("📋 전체 접수 내역 및 조치 등록")
        df = load_data()

        if df.empty:
            st.info("현재 접수된 내역이 없습니다.")
        else:
            st.dataframe(df, use_container_width=True)
            st.markdown("---")

            # 1. 조치 업데이트
            st.subheader("✏️ 조치 상태 및 내용 업데이트")
            
            options = [
                f"{idx}번 | [{row.get('접수일시', '')}] {row.get('시설ID', '')} ({row.get('고장유형', '')})" 
                for idx, row in df.iterrows()
            ]
            selected_option = st.selectbox("수정할 접수 건을 선택하세요:", options, key="edit_select")
            
            selected_idx = int(selected_option.split("번")[0])
            target_row = df.loc[selected_idx]

            if target_row.get("사진URL", "없음") != "없음" and pd.notna(target_row.get("사진URL")):
                st.image(target_row["사진URL"], caption="첨부된 현장 사진", width=300)

            col_a, col_b = st.columns(2)
            with col_a:
                curr_status = target_row.get("처리상태", "접수완료")
                status_list = ["접수완료", "처리중", "완료", "보류"]
                status_idx = status_list.index(curr_status) if curr_status in status_list else 0
                
                new_status = st.selectbox(
                    "처리 상태 변경", 
                    status_list,
                    index=status_idx,
                    key="status_select"
                )
            with col_b:
                action_detail = st.text_area("조치 내용", value=str(target_row.get("조치내용", "")) if pd.notna(target_row.get("조치내용")) else "", key="action_text")

            if st.button("💾 조치 사항 저장하기", use_container_width=True, key="save_btn"):
                df.loc[selected_idx, "처리상태"] = new_status
                df.loc[selected_idx, "조치내용"] = action_detail
                df.loc[selected_idx, "조치일시"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                conn.update(data=df)
                st.success("조치 결과가 구글 시트에 업데이트되었습니다!")
                st.rerun()

            st.markdown("---")

            # 2. 접수 내역 삭제
            st.subheader("🗑️ 접수 내역 삭제 (강제 삭제)")
            st.warning("⚠️ 삭제된 내역은 복구할 수 없습니다.")

            del_options = [
                f"{idx}번 | [{row.get('접수일시', '')}] {row.get('시설ID', '')} - {str(row.get('고장내용', ''))[:15]}..." 
                for idx, row in df.iterrows()
            ]
            selected_del_option = st.selectbox("삭제할 접수 건 선택:", del_options, key="del_select")
            del_idx = int(selected_del_option.split("번")[0])

            if st.button("🔴 선택한 내역 삭제하기", use_container_width=True, key="del_btn"):
                df_deleted = df.drop(index=del_idx).reset_index(drop=True)
                conn.update(data=df_deleted)
                st.success(f"✅ {del_idx}번 접수 내역이 성공적으로 삭제되었습니다.")
                st.rerun()


# =========================================================
# TAB 3: 개선 결과 통계 (엑셀 다운로드 기능 추가)
# =========================================================
with tab3:
    if check_password(key_prefix="tab3"):
        st.subheader("📊 시설보수 처리 현황 및 통계")
        df = load_data()

        if df.empty:
            st.info("통계를 산출할 데이터가 없습니다.")
        else:
            # --- 📥 엑셀 다운로드 버튼 영역 ---
            excel_data = create_excel_report(df)
            file_today = datetime.now().strftime("%Y%m%d_%H%M")
            
            st.download_button(
                label="📥 전체 통계 및 접수 내역 엑셀 다운로드 (.xlsx)",
                data=excel_data,
                file_name=f"시설보수_통계보고서_{file_today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            st.markdown("---")

            # 주요 KPI 지표
            total_count = len(df)
            completed_count = len(df[df["처리상태"] == "완료"])
            in_progress_count = len(df[df["처리상태"] == "처리중"])
            pending_count = len(df[df["처리상태"] == "접수완료"])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 접수 건수", f"{total_count}건")
            c2.metric("처리 완료", f"{completed_count}건")
            c3.metric("처리 중", f"{in_progress_count}건")
            c4.metric("미처리 접수", f"{pending_count}건")

            st.markdown("---")

            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.write("##### 📌 처리 상태별 현황")
                status_counts = df["처리상태"].value_counts()
                st.bar_chart(status_counts)

            with col_chart2:
                st.write("##### 🏷️ 고장 유형별 접수 비중")
                type_counts = df["고장유형"].value_counts()
                st.bar_chart(type_counts)
