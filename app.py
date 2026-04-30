import streamlit as st
import pandas as pd
from pathlib import Path
from streamlit_folium import folium_static
import sys
import os
import datetime


sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from generate_folium_map import load_csv, prepare_house_scores, create_map
current_year = datetime.datetime.now().year
BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(page_title="최적 자취방 탐색기", layout="wide")

st.title("동의대 자취방 추천 시스템")

with st.sidebar:
    st.header("필수 조건")
    st.markdown("이 조건을 벗어나는 매물은 아예 제외됩니다.")
    
    max_deposit = st.slider("최대 보증금/전세 (만원)", min_value=0, max_value=10000, value=5000, step=100, format="%d만")
    max_rent = st.slider("최대 월세 (만원)", min_value=0, max_value=200, value=50, step=5, format="%d만")
    max_dist = st.slider("최대 학교 거리 (km)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    max_year = st.slider("최대 건물 연식 (년)", min_value=0, max_value=100, value=30, step=1)
    
    st.divider()

    st.header("조건 가중치")
    
    # 월세 가중치
    weight_rent = st.slider("월세 (가격 중요도)", 0, 100, 40)
    
    # 거리 가중치
    max_dist_weight = 100 - weight_rent
    if max_dist_weight > 0:
        weight_dist = st.slider("거리 (학교 접근성)", 0, max_dist_weight, min(40, max_dist_weight))
    else:
        st.slider("거리 (학교 접근성)", min_value=0, max_value=1, value=0, disabled=True)
        weight_dist = 0
        
    # 연식 가중치 
    max_year_weight = 100 - weight_rent - weight_dist
    if max_year_weight > 0:
        weight_year = st.slider("연식 (건물 상태)", 0, max_year_weight, min(20, max_year_weight))
    else:
        st.slider("연식 (건물 상태)", min_value=0, max_value=1, value=0, disabled=True)
        weight_year = 0
        
    current_total = weight_rent + weight_dist + weight_year
    st.caption(f"현재 가중치 총합: {current_total} / 100점")
    
    st.divider()

    st.header("인프라 가산점 (선택 시 활성화)")
    use_subway = st.checkbox("지하철역 가점 (최대 12점)", value=True)
    use_bus = st.checkbox("버스정류장 가점 (최대 6점)", value=True)
    use_cctv = st.checkbox("방범용 CCTV 가점 (100m 이내 개당 +3점 최대 9점)", value=True)
    
    st.divider()

    st.header("결과 설정")
    top_n = st.slider("지도 표시 상위 매물 수", 5, 50, 20)

# 데이터 캐싱 
@st.cache_data
def load_all_data():
    house_df = load_csv(BASE_DIR / "data" / "house_with_coordinates.csv")
    bus_df = load_csv(BASE_DIR / "data" / "cleaned_BUS.csv")
    cctv_df = load_csv(BASE_DIR / "data" / "cleaned_CCTV.csv")
    subway_df = load_csv(BASE_DIR / "data" / "cleaned_SUBWAY.csv")
    return house_df, bus_df, cctv_df, subway_df

house_df, bus_df, cctv_df, subway_df = load_all_data()

# 체크박스 상태에 따라 인프라 데이터 활성/비활성 
active_subway = subway_df if use_subway else pd.DataFrame()
active_bus = bus_df if use_bus else pd.DataFrame()
active_cctv = cctv_df if use_cctv else pd.DataFrame()

with st.spinner("조건에 맞는 최적의 자취방을 계산하고 있습니다..."):
    # 원본 데이터로 전체 점수 연산
    scored_df = prepare_house_scores(
        house_df, active_bus, active_cctv, active_subway, 
        weight_rent, weight_dist, weight_year
    )
    
    # 사용자가 설정한 최대값 이하인 매물만 남김
    filtered_df = scored_df[
        (scored_df['보증금_정수'].fillna(0) <= max_deposit) &
        (scored_df['월세_정수'].fillna(0) <= max_rent) &
        (scored_df['학교거리_km'] <= max_dist) &
        ((current_year - scored_df['건축년도_정수'].fillna(current_year)) <= max_year)
        ].copy()

    # 중복 건물 제거
    filtered_df = filtered_df.drop_duplicates(subset=["위도", "경도"]).reset_index(drop=True)
    
    # 필터링 후 남은 매물 개수 파악
    display_count = min(top_n, len(filtered_df))

if len(filtered_df) == 0:
    st.error("조건에 맞는 매물이 없습니다. 보증금이나 월세, 거리 조건을 조금 더 완화해 보세요!")
else:
    st.success(f"전체 {len(house_df)}개의 매물 중 조건에 맞는 {len(filtered_df)}개의 방을 찾았습니다!")
    
    map_placeholder = st.empty()

    # 화면 아래쪽에 상세 데이터 표
    st.subheader(f"상위 {display_count}개 추천 매물 상세 정보")
    
    original_cols = ['건물명', '보증금(만원)', '월세금(만원)', '학교거리_km', '건축년도_정수', '최소_지하철_거리_km', '최소_버스_거리_km', '최적점수']
    display_df = filtered_df.head(display_count)[original_cols].copy()

    display_df['학교거리_km'] = display_df['학교거리_km'].round(2)
    display_df['건축년도_정수'] = display_df['건축년도_정수'].astype(int)
    display_df['최소_지하철_거리_km'] = display_df['최소_지하철_거리_km'].apply(lambda x: round(x, 2) if x != float('inf') else '-')
    display_df['최소_버스_거리_km'] = display_df['최소_버스_거리_km'].apply(lambda x: round(x, 2) if x != float('inf') else '-')
    display_df['최적점수'] = display_df['최적점수'].round(1)

    display_df.columns = ['건물명', '보증금', '월세금', '학교거리', '건축년도', '지하철거리', '버스거리', '최종점수']

    event = st.dataframe(
        display_df, 
        use_container_width=True,
        on_select="rerun",          
        selection_mode="single-row" 
    )

    focus_lat, focus_lon = None, None
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0] 
        focus_lat = filtered_df.iloc[selected_idx]['위도']
        focus_lon = filtered_df.iloc[selected_idx]['경도']

    with map_placeholder:
        fmap = create_map(filtered_df, active_bus, active_cctv, active_subway, display_count, focus_lat, focus_lon)
        folium_static(fmap, width=1300, height=600)