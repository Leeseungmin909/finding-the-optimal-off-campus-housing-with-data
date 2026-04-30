import pandas as pd

# 자취방 데이터 정제
df_house = pd.read_excel('data/HOUSE.xlsx')

# 실제 엑셀 파일의 컬럼명에 맞게 리스트 수정
room_cols = ['시군구', '번지', '본번', '부번', '건물명', '전월세구분', '전용면적(㎡)', '계약년월', '보증금(만원)', '월세금(만원)', '층', '건축년도']
df_house = df_house[room_cols]

# 결측치 제거
df_house = df_house.dropna()

# 주소 분리
addr_split = df_house['시군구'].str.split(' ', expand=True)
df_house['시도'] = addr_split[0]
df_house['구'] = addr_split[1]
df_house['법정동'] = addr_split[2]

# 전용면적 9평미만 필터링
df_house = df_house[df_house['전용면적(㎡)'] <= 30]

# CCTV 데이터 정제
df_cctv = pd.read_csv('data/CCTV.csv', encoding='cp949')
df_cctv = df_cctv[['위도', '경도']]
df_cctv = df_cctv.dropna()

# 버스 데이터정제
df_bus = pd.read_excel('data/BUS.xlsx')
df_bus = df_bus[['위도', '경도', '정류장명']]
df_bus = df_bus.dropna()

# 지하철 데이터 정제
df_subway = pd.read_excel('data/SUBWAY.xlsx')
df_subway = df_subway[['역명', '위도', '경도', '호선']]
df_subway = df_subway.dropna()

# 정제된 데이터를 새로운 파일로 저장
df_house.to_csv('data/cleaned_HOUSE.csv', index=False, encoding='utf-8-sig')
df_cctv.to_csv('data/cleaned_CCTV.csv', index=False, encoding='utf-8-sig')
df_bus.to_csv('data/cleaned_BUS.csv', index=False, encoding='utf-8-sig')
df_subway.to_csv('data/cleaned_SUBWAY.csv', index=False, encoding='utf-8-sig')