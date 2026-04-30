# Finding the Optimal Off-Campus Housing with Data

부산 지역(동의대학교 인근) 자취방 데이터를 정제하고, 공간정보 오픈 API(VWorld)와 자체 입지 분석 알고리즘을 결합하여 최적의 자취방을 추천해 주는 Streamlit 기반 인터랙티브 웹 대시보드입니다.

## 프로젝트 화면 (미리보기)
<img width="1901" height="945" alt="image" src="https://github.com/user-attachments/assets/cfbf82a9-3c7b-4cd4-86db-c5e9138d1197" />

## 디렉토리 구조

```text
📦 Finding-the-Optimal-Off-Campus-Housing-with-Data
 ┣ 📂 data           # 원본 및 정제된 CSV 데이터 폴더
 ┣ 📂 src            # 데이터 전처리 및 지도 생성 핵심 모듈
 ┃ ┣ 📜 data.py
 ┃ ┣ 📜 enrich_house_coordinates.py
 ┃ ┣ 📜 generate_folium_map.py
 ┃ ┣ 📜 pnu_generator.py
 ┃ ┗ 📜 vworld_client.py
 ┣ 📜 app.py         # Streamlit 웹 대시보드 메인 실행 파일
 ┣ 📜 requirements.txt
 ┣ 📜 README.md
 ┗ 📜 .gitignore
```

## 프로젝트 파이프라인 
1. `src/data.py`
   원본 자취방/버스/CCTV/지하철 데이터를 정제해 `cleaned_*.csv`로 저장합니다.
2. `src/pnu_generator.py`
   자취방 주소를 기반으로 법정동코드와 PNU를 생성합니다.
3. `src/enrich_house_coordinates.py`
   VWorld API를 호출하여 주소 및 PNU 기반으로 자취방별 위도/경도를 조회하고 좌표 데이터를 확보합니다.
4. `src/generate_folium_map.py`
   동적 가중치 연산 및 Folium 기반 히트맵, 후보 자취방 마커 시각화 로직을 처리합니다.
5. `app.py`
   Streamlit 기반의 대시보드 웹 UI를 생성하고 데이터 분석 결과와 지도를 화면에 통합 렌더링합니다.


## 가상환경 및 라이브러리 설치

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## API 키 관리

프로젝트 루트에 `.env` 파일을 만들고 아래처럼 VWorld API 키를 넣어두면 됩니다.

```bash
cp .env .env
```

`.env`

```env
VWORLD_API_KEY=YOUR_VWORLD_API_KEY
```

## 실행 순서
터미널에 아래 명령어를 순서대로 입력합니다. (데이터 정제는 최초 1회만 실행해도 무방합니다.)

```bash
python src/data.py
python src/pnu_generator.py
python src/enrich_house_coordinates.py
streamlit run app.py
```

명령어를 입력하면 브라우저가 자동 실행되며 웹 대시보드가 열립니다.
좌측 사이드바에서 가중치를 실시간으로 조절하며 지도의 변화를 확인할 수 있으며, 매물 표의 항목을 클릭하면 해당 위치로 지도가 이동합니다.

## 코어 점수 
사용자가 웹 대시보드에서 직접 설정한 가중치를 바탕으로 정규화하여 계산합니다.
- **월세:** 가격이 낮을수록 높은 점수 할당 
- **학교 거리:** 동의대 정문 기준, 직선거리가 가까울수록 높은 점수 할당 
- **건물 연식:** 최근에 건축된 매물일수록 높은 점수 할당

## 알파 점수 
단순히 반경 내 개수를 세는 것을 넘어, '매물과 인프라 사이의 거리'에 따라 점수가 연속적으로 차등 지급되는 거리 감쇠 로직을 적용했습니다.
- **지하철 접근성:** 반경 800m 이내 접근 시, 거리가 가까울수록 보너스 점수 점진적 증가 (최대 12점)
- **버스 접근성:** 반경 500m 이내 접근 시, 거리가 가까울수록 보너스 점수 점진적 증가 (최대 5점)
- **방범 안전성:** 반경 150m 이내 방범용 CCTV 밀집도에 비례하여 안전 점수 부여 (최대 3점)
