import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
import time  
from streamlit_gsheets import GSheetsConnection

# --- 0. 웹페이지 기본 설정 ---
st.set_page_config(page_title="트인 마일리지", page_icon="🏆")

# --- 1. 구글 시트 연결 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"구글 시트 연결 오류: {e}")
    st.stop()

# --- 2. 데이터 불러오기 함수 ---
def load_data(sheet_name):
    try:
        # 🚀 API 과부하를 막기 위해 평상시에는 10분(600초) 단위로 캐시를 유지합니다.
        df = conn.read(worksheet=sheet_name, ttl=600)
        if df.empty:
             if sheet_name == "admins":
                 return pd.DataFrame(columns=["admin_id", "password"])
             elif sheet_name == "users":
                 return pd.DataFrame(columns=["user_id", "points"])
             elif sheet_name == "logs":
                 return pd.DataFrame(columns=["granted_at", "admin_id", "user_id", "points", "reason"])
             elif sheet_name == "requests":
                 return pd.DataFrame(columns=["requested_at", "user_id", "reason", "status"])
        return df
    except Exception as e:
        st.error(f"{sheet_name} 시트를 읽어오는 중 오류가 발생했습니다: {e}")
        st.stop()

# --- 3. 데이터 저장(업데이트) 함수 ---
def save_data(sheet_name, df):
    try:
        conn.update(worksheet=sheet_name, data=df)
        st.cache_data.clear() # 데이터가 변경될 때는 즉시 캐시를 강제 삭제하여 최신화합니다.
        time.sleep(1.5) 
    except Exception as e:
         st.error(f"{sheet_name} 시트를 저장하는 중 오류가 발생했습니다: {e}")

# --- 4. 자동 로그인 및 상태 초기화 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_admin = ""

# --- 5. 사이드바 (로그인/로그아웃) ---
with st.sidebar:
    st.title("🔒 운영자 로그인")
    
    if not st.session_state.logged_in:
        st.write("운영자 전용 메뉴입니다.")
        login_id = st.text_input("아이디")
        login_pw = st.text_input("비밀번호", type="password") 
        
        if st.button("로그인"):
            df_admins = load_data("admins")
            match = df_admins[(df_admins['admin_id'].astype(str) == str(login_id)) & 
                              (df_admins['password'].astype(str) == str(login_pw))]
            
            if not match.empty:
                st.session_state.logged_in = True
                st.session_state.current_admin = login_id
                st.rerun() 
            else:
                st.error("아이디 또는 비밀번호가 다릅니다.")
    else:
        st.success(f"환영합니다, **{st.session_state.current_admin}**님!")
        if st.button("로그아웃"):
            st.session_state.logged_in = False
            st.session_state.current_admin = ""
            st.rerun()

# --- 6. 메인 화면 구성 ---
st.title("🏆 트인 마일리지")

if st.session_state.logged_in:
    tabs = st.tabs(["리더보드 & 내역", "마일리지 승인 및 관리", "시스템 관리"])
    tab1, tab_admin_manage, tab_admin_system = tabs[0], tabs[1], tabs[2]
else:
    tabs = st.tabs(["리더보드 & 내역", "🙋‍♀️ 마일리지 신청"])
    tab1, tab_user_request = tabs[0], tabs[1]

# --- TAB 1: 리더보드 및 로그 (공통) ---
with tab1:
    st.header("🏆 마일리지 랭킹 보드")
    df_users = load_data("users")
    
    if not df_users.empty and len(df_users) > 0:
        df_users['points'] = pd.to_numeric(df_users['points'], errors='coerce').fillna(0)
        df_rank = df_users.sort_values(by='points', ascending=False).reset_index(drop=True)
        df_rank.index = df_rank.index + 1 
        df_rank.columns = ['사용자', '점수']
        st.dataframe(df_rank, use_container_width=True)
    else:
        st.info("현재 등록된 사용자가 없습니다.")
        
    st.divider()
    st.header("📝 최근 마일리지 내역")
    df_logs = load_data("logs")
    
    if not df_logs.empty and len(df_logs) > 0:
        df_logs.fillna("", inplace=True)
        df_display = df_logs.iloc[::-1].head(20).reset_index(drop=True)
        df_display.columns = ['시간', '운영자', '대상자', '변동 점수', '사유']
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("최근 내역이 없습니다.")


# ==========================================
# 일반 사용자 전용 탭 (로그아웃 상태)
# ==========================================
if not st.session_state.logged_in:
    
    with tab_user_request:
        st.header("🙋‍♀️ 마일리지 신청하기")
        st.write("활동을 증빙할 수 있는 사유를 적어 마일리지를 신청해 주세요.")
        
        df_users = load_data("users")
        user_list = df_users['user_id'].tolist() if not df_users.empty else []
        
        if not user_list:
            st.warning("등록된 사용자가 없습니다. 먼저 운영자에게 아이디 등록을 요청하세요.")
        else:
            with st.form("user_request_form"):
                req_user = st.selectbox("본인 아이디 선택", user_list)
                req_reason = st.text_input("마일리지 신청 사유 (자세히 적어주세요)")
                submitted_req = st.form_submit_button("신청하기")
                
                if submitted_req:
                    if not req_reason.strip():
                        st.warning("⚠️ 신청 사유를 비워둘 수 없습니다.")
                    else:
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        df_req = load_data("requests")
                        new_req = pd.DataFrame([{
                            "requested_at": now, 
                            "user_id": req_user, 
                            "reason": req_reason, 
                            "status": "pending"
                        }])
                        df_updated_req = pd.concat([df_req, new_req], ignore_index=True)
                        save_data("requests", df_updated_req)
                        st.toast(f"✅ {req_user}님의 마일리지 신청이 접수되었습니다!", icon="✅")
                        st.rerun() 


# ==========================================
# 운영자 전용 탭 (로그인 상태)
# ==========================================
if st.session_state.logged_in:
    
    with tab_admin_manage:
        st.header("📋 마일리지 신청 승인 대기열")
        
        df_req = load_data("requests")
        pending_requests = df_req[df_req['status'] == 'pending'] if not df_req.empty else pd.DataFrame()
        
        if pending_requests.empty:
            st.info("🎉 현재 대기 중인 마일리지 신청이 없습니다.")
        else:
            for index, row in pending_requests.iterrows():
                r_time = row['requested_at']
                r_user = row['user_id']
                r_reason = row['reason']
                
                with st.container():
                    st.write(f"**신청자:** {r_user} | **신청 시간:** {r_time}")
                    st.write(f"📝 **신청 사유:** {r_reason}")
                    
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        pts_to_give = st.number_input("부여할 점수 입력", min_value=1, step=10, key=f"pts_{index}")
                    with col2:
                        st.write("") 
                        if st.button("✅ 점수 부여", key=f"btn_ok_{index}", use_container_width=True):
                            df_users = load_data("users")
                            user_idx = df_users.index[df_users['user_id'] == r_user].tolist()[0]
                            current_pts = pd.to_numeric(df_users.at[user_idx, 'points'])
                            df_users.at[user_idx, 'points'] = current_pts + pts_to_give
                            save_data("users", df_users)
                            
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            df_logs = load_data("logs")
                            new_log = pd.DataFrame([{
                                "granted_at": now, 
                                "admin_id": st.session_state.current_admin, 
                                "user_id": r_user, 
                                "points": pts_to_give, 
                                "reason": r_reason
                            }])
                            df_updated_logs = pd.concat([df_logs, new_log], ignore_index=True)
                            save_data("logs", df_updated_logs)
                            
                            df_req.at[index, 'status'] = 'approved'
                            save_data("requests", df_req)
                            
                            st.toast(f"{r_user}님에게 {pts_to_give}점을 부여했습니다!", icon="✅")
                            st.rerun()
                    with col3:
                        st.write("") 
                        if st.button("❌ 반려", key=f"btn_no_{index}", use_container_width=True):
                            df_req.at[index, 'status'] = 'rejected'
                            save_data("requests", df_req)
                            st.toast("해당 요청을 반려했습니다.", icon="🗑️")
                            st.rerun()
                    st.markdown("---")
        
        with st.expander("🛠️ 수동 마일리지 차감 (마일리지 사용 시)"):
            df_users = load_data("users")
            user_list = df_users['user_id'].tolist() if not df_users.empty else []
            
            if user_list:
                with st.form("manual_deduct"):
                    del_user = st.selectbox("점수 차감 대상자", user_list)
                    del_pts = st.number_input("차감할 점수", min_value=1, step=10)
                    del_reason = st.text_input("차감 사유 (필수)")
                    if st.form_submit_button("➖ 수동 차감 실행"):
                        if not del_reason:
                            st.warning("차감 사유를 입력해주세요.")
                        else:
                            user_idx = df_users.index[df_users['user_id'] == del_user].tolist()[0]
                            current_pts = pd.to_numeric(df_users.at[user_idx, 'points'])
                            df_users.at[user_idx, 'points'] = current_pts - del_pts
                            save_data("users", df_users)
                            
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            df_logs = load_data("logs")
                            new_log = pd.DataFrame([{
                                "granted_at": now, 
                                "admin_id": st.session_state.current_admin, 
                                "user_id": del_user, 
                                "points": -del_pts, 
                                "reason": f"[수동차감] {del_reason}"
                            }])
                            df_updated_logs = pd.concat([df_logs, new_log], ignore_index=True)
                            save_data("logs", df_updated_logs)
                            
                            st.toast(f"{del_user}님의 점수가 차감되었습니다.", icon="📉")
                            st.rerun()

    with tab_admin_system:
        st.header("⚙️ 시스템 관리")
        
        st.subheader("➕ 계정 등록하기")
        col_add1, col_add2 = st.columns(2)
        
        with col_add1:
            st.write("👨‍💻 운영자 추가")
            with st.form("add_admin_form"):
                new_admin = st.text_input("새 운영자 ID")
                new_admin_pw = st.text_input("새 운영자 비밀번호", type="password")
                if st.form_submit_button("운영자 등록"):
                    if new_admin and new_admin_pw:
                        df_admins = load_data("admins")
                        if new_admin in df_admins['admin_id'].values:
                            st.error("이미 존재하는 운영자입니다.")
                        else:
                            new_admin_df = pd.DataFrame([{"admin_id": new_admin, "password": new_admin_pw}])
                            df_updated_admins = pd.concat([df_admins, new_admin_df], ignore_index=True)
                            save_data("admins", df_updated_admins)
                            st.success(f"'{new_admin}' 운영자 등록 완료!")
                            st.rerun() 
                    else:
                        st.warning("아이디와 비밀번호를 모두 입력해주세요.")
                        
        with col_add2:
            st.write("👤 일반 사용자 추가")
            with st.form("add_user_form_admin"):
                new_admin_user_id = st.text_input("새 사용자 ID")
                if st.form_submit_button("사용자 등록"):
                    if new_admin_user_id.strip():
                        df_users = load_data("users")
                        if new_admin_user_id in df_users['user_id'].values:
                            st.error("이미 존재하는 사용자입니다.")
                        else:
                            new_user = pd.DataFrame([{"user_id": new_admin_user_id, "points": 0}])
                            df_updated_users = pd.concat([df_users, new_user], ignore_index=True)
                            save_data("users", df_updated_users)
                            st.success(f"'{new_admin_user_id}' 사용자 등록 완료!")
                            st.rerun() 
                    else:
                        st.warning("아이디를 입력해주세요.")

        st.divider() 
        
        st.subheader("➖ 계정 삭제하기")
        df_admins = load_data("admins")
        df_users = load_data("users")
        
        all_admins = df_admins['admin_id'].tolist() if not df_admins.empty else []
        all_users = df_users['user_id'].tolist() if not df_users.empty else []
        
        col_del1, col_del2 = st.columns(2)
        with col_del1:
            st.write("운영자 삭제")
            if all_admins:
                del_admin = st.selectbox("삭제할 운영자 선택", all_admins)
                if st.button("운영자 삭제"):
                    if del_admin == st.session_state.current_admin:
                        st.error("현재 로그인 중인 본인 계정은 삭제할 수 없습니다.")
                    else:
                        df_admins = df_admins[df_admins['admin_id'] != del_admin]
                        save_data("admins", df_admins)
                        st.success("삭제 완료!")
                        st.rerun() 
            else:
                st.info("등록된 운영자가 없습니다.")
                
        with col_del2:
            st.write("일반 사용자 삭제")
            if all_users:
                del_user_target = st.selectbox("삭제할 사용자 선택", all_users)
                if st.button("사용자 삭제"):
                    df_users = df_users[df_users['user_id'] != del_user_target]
                    save_data("users", df_users)
                    st.success("삭제 완료!")
                    st.rerun() 
            else:
                st.info("등록된 일반 사용자가 없습니다.")
