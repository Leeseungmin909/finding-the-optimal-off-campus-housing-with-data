from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
except ImportError as exc:
    raise ImportError(
        "folium이 설치되어 있지 않습니다. `pip install -r requirements.txt`를 먼저 실행해주세요."
    ) from exc


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HOUSE_PATH = BASE_DIR / "data" / "house_with_coordinates.csv"
DEFAULT_BUS_PATH = BASE_DIR / "data" / "cleaned_BUS.csv"
DEFAULT_CCTV_PATH = BASE_DIR / "data" / "cleaned_CCTV.csv"
DEFAULT_SUBWAY_PATH = BASE_DIR / "data" / "cleaned_SUBWAY.csv"
DEFAULT_OUTPUT_PATH = BASE_DIR / "outputs" / "optimal_room_map.html"

# 동의대학교 정문 좌표 
UNI_LAT = 35.1425
UNI_LON = 129.0347


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Folium 기반 최적 자취방 지도(동적 가중치 및 거리감쇠 적용)를 생성합니다.")
    parser.add_argument("--house-path", default=str(DEFAULT_HOUSE_PATH), help="자취방 CSV 경로")
    parser.add_argument("--bus-path", default=str(DEFAULT_BUS_PATH), help="버스 CSV 경로")
    parser.add_argument("--cctv-path", default=str(DEFAULT_CCTV_PATH), help="CCTV CSV 경로")
    parser.add_argument("--subway-path", default=str(DEFAULT_SUBWAY_PATH), help="지하철 CSV 경로")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="출력 HTML 경로")
    parser.add_argument("--top-n", type=int, default=20, help="마커로 강조할 상위 자취방 개수")
    
    # 동적 가중치 입력 파라미터 
    parser.add_argument("--weight-rent", type=float, default=40.0, help="월세 가중치 (기본: 40)")
    parser.add_argument("--weight-dist", type=float, default=40.0, help="학교거리 가중치 (기본: 40)")
    parser.add_argument("--weight-year", type=float, default=20.0, help="건물연식 가중치 (기본: 20)")
    return parser.parse_args()


def load_csv(path: str | Path, optional: bool = False) -> pd.DataFrame:
    if optional and not os.path.exists(path):
        print(f"안내: 선택적 데이터 파일이 존재하지 않아 빈 데이터로 처리합니다 -> {path}")
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def sanitize_coordinate_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    sanitized = df.copy()
    sanitized["위도"] = pd.to_numeric(sanitized["위도"], errors="coerce")
    sanitized["경도"] = pd.to_numeric(sanitized["경도"], errors="coerce")
    sanitized = sanitized.dropna(subset=["위도", "경도"]).copy()
    return sanitized


def parse_money(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .replace({"": np.nan, "nan": np.nan})
        .astype(float)
    )


def normalize(series: pd.Series, inverse: bool = False) -> pd.Series:
    series = series.astype(float)
    min_value = series.min()
    max_value = series.max()

    if pd.isna(min_value) or pd.isna(max_value) or min_value == max_value:
        normalized = pd.Series(1.0, index=series.index)
    else:
        normalized = (series - min_value) / (max_value - min_value)

    return 1.0 - normalized if inverse else normalized


def get_distances_vectorized(lat1: float, lon1: float, lat2_array: np.ndarray, lon2_array: np.ndarray) -> np.ndarray:
    """거리 연산 (단위: km)"""
    R = 6371.0
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2, lon2 = np.radians(lat2_array), np.radians(lon2_array)
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c


def prepare_house_scores(
    house_df: pd.DataFrame,
    bus_df: pd.DataFrame,
    cctv_df: pd.DataFrame,
    subway_df: pd.DataFrame,
    weight_rent: float,
    weight_dist: float,
    weight_year: float,
) -> pd.DataFrame:
    df = sanitize_coordinate_columns(house_df)

    df["월세_정수"] = parse_money(df["월세금(만원)"])
    df["보증금_정수"] = parse_money(df["보증금(만원)"])
    df["전용면적_정수"] = pd.to_numeric(df["전용면적(㎡)"], errors="coerce")
    df["건축년도_정수"] = pd.to_numeric(df["건축년도"], errors="coerce")

    # 동의대와의 거리 계산
    df['학교거리_km'] = get_distances_vectorized(UNI_LAT, UNI_LON, df['위도'].values, df['경도'].values)

    # 인프라 좌표 추출
    bus_points = sanitize_coordinate_columns(bus_df)
    cctv_points = sanitize_coordinate_columns(cctv_df)
    subway_points = sanitize_coordinate_columns(subway_df)

    bus_lats = bus_points['위도'].values if not bus_points.empty else np.array([])
    bus_lons = bus_points['경도'].values if not bus_points.empty else np.array([])
    
    cctv_lats = cctv_points['위도'].values if not cctv_points.empty else np.array([])
    cctv_lons = cctv_points['경도'].values if not cctv_points.empty else np.array([])
    
    sub_lats = subway_points['위도'].values if not subway_points.empty else np.array([])
    sub_lons = subway_points['경도'].values if not subway_points.empty else np.array([])

    min_bus_dist, min_sub_dist, cctv_counts = [], [], []

    # 매물별 최소 거리 및 개수 연산
    for h_lat, h_lon in zip(df['위도'].values, df['경도'].values):
        if len(bus_lats) > 0:
            min_bus_dist.append(get_distances_vectorized(h_lat, h_lon, bus_lats, bus_lons).min())
        else:
            min_bus_dist.append(float('inf'))
            
        if len(sub_lats) > 0:
            min_sub_dist.append(get_distances_vectorized(h_lat, h_lon, sub_lats, sub_lons).min())
        else:
            min_sub_dist.append(float('inf'))
            
        if len(cctv_lats) > 0:
            c_dists = get_distances_vectorized(h_lat, h_lon, cctv_lats, cctv_lons)
            cctv_counts.append((c_dists <= 0.15).sum())
        else:
            cctv_counts.append(0)

    df['최소_버스_거리_km'] = min_bus_dist
    df['최소_지하철_거리_km'] = min_sub_dist
    df['주변_CCTV_수'] = cctv_counts

    # 알파 점수 (연속적 거리 감쇠)
    df['알파_지하철'] = np.where(df['최소_지하철_거리_km'] <= 0.1, 12.0,
                         np.where(df['최소_지하철_거리_km'] <= 0.8, 12.0 * (0.8 - df['최소_지하철_거리_km']) / 0.7, 0.0))
    df['알파_버스'] = np.where(df['최소_버스_거리_km'] <= 0.1, 5.0,
                       np.where(df['최소_버스_거리_km'] <= 0.5, 5.0 * (0.5 - df['최소_버스_거리_km']) / 0.4, 0.0))
    df['알파_CCTV'] = np.clip(df['주변_CCTV_수'] * 1.0, 0, 3.0)

    df['알파점수(보너스)'] = df['알파_지하철'] + df['알파_버스'] + df['알파_CCTV']

    # 정규화 후 사용자 가중치 반영
    df["n_rent"] = normalize(df["월세_정수"], inverse=True)    
    df["n_dist"] = normalize(df["학교거리_km"], inverse=True)   
    df["n_year"] = normalize(df["건축년도_정수"], inverse=False)  

    df["코어점수(100점)"] = (weight_rent * df["n_rent"]) + (weight_dist * df["n_dist"]) + (weight_year * df["n_year"])

    # 최종 스코어
    df["최적점수"] = df["코어점수(100점)"] + df["알파점수(보너스)"]

    return df.sort_values("최적점수", ascending=False).reset_index(drop=True)


def format_popup_html(row: pd.Series) -> str:
    total_score = round(float(row["최적점수"]), 2)
    core_score = round(float(row["코어점수(100점)"]), 2)
    alpha_score = round(float(row["알파점수(보너스)"]), 2)
    distance = round(float(row["학교거리_km"]), 2)
    deposit = row["보증금(만원)"]
    monthly = row["월세금(만원)"]
    year = int(row["건축년도_정수"]) if pd.notna(row["건축년도_정수"]) else "-"

    bus_dist = float(row['최소_버스_거리_km'])
    sub_dist = float(row['최소_지하철_거리_km'])
    bus_str = f"{round(bus_dist * 1000)}m" if bus_dist != float('inf') else "정보 없음"
    sub_str = f"{round(sub_dist * 1000)}m" if sub_dist != float('inf') else "정보 없음"

    return f"""
    <div style="width:260px; font-family: sans-serif;">
      <h4 style="margin-bottom:8px; color:#1a73e8;">{row.get('건물명', '자취방')}</h4>
      <p style="margin:2px 0;"><b>유형</b>: {row['전월세구분']}</p>
      <p style="margin:2px 0;"><b>보증금/월세</b>: {deposit} / {monthly}</p>
      <p style="margin:2px 0;"><b>건축년도</b>: {year}년</p>
      <hr style="margin: 8px 0; border: 0; border-top: 1px solid #eee;">
      <p style="margin:2px 0; color:#d93025;"><b>동의대까지 거리</b>: {distance}km</p>
      <p style="margin:2px 0;">최소 버스 거리: {bus_str}</p>
      <p style="margin:2px 0;">최소 지하철 거리: {sub_str}</p>
      <hr style="margin: 8px 0; border: 0; border-top: 1px solid #eee;">
      <p style="margin:2px 0;"><b>코어 점수</b>: {core_score}</p>
      <p style="margin:2px 0;"><b>알파 점수</b>: +{alpha_score}</p>
      <h3 style="margin:6px 0 0; color:#188038;">총점: {total_score}점</h3>
    </div>
    """


def add_top_room_markers(fmap: folium.Map, scored_df: pd.DataFrame, top_n: int) -> None:
    top_df = scored_df.head(top_n)
    
    house_group = folium.FeatureGroup(name=f"상위 {top_n}개 자취방", show=True).add_to(fmap)

    for rank, (_, row) in enumerate(top_df.iterrows(), start=1):
        popup = folium.Popup(format_popup_html(row), max_width=320)
        tooltip = f"{rank}위 | 점수 {row['최적점수']:.1f}"
        
        folium.Marker(
            location=[row["위도"], row["경도"]],
            popup=popup,
            tooltip=tooltip,
            icon=folium.Icon(color="red", icon="home", prefix="fa"),
        ).add_to(house_group) 


def add_reference_layers(fmap: folium.Map, bus_df: pd.DataFrame, cctv_df: pd.DataFrame, subway_df: pd.DataFrame, scored_df: pd.DataFrame) -> None:
    bus_df = sanitize_coordinate_columns(bus_df)
    cctv_df = sanitize_coordinate_columns(cctv_df)
    subway_df = sanitize_coordinate_columns(subway_df)

    margin = 0.008 # 상위 자취방 기준 딱 800m 반경까지만 여백 설정
    
    min_lat, max_lat = scored_df["위도"].min() - margin, scored_df["위도"].max() + margin
    min_lon, max_lon = scored_df["경도"].min() - margin, scored_df["경도"].max() + margin

    # 지정된 인프라 범위 외 데이터는 전부 잘라내는 함수
    def filter_bounds(df):
        if df.empty: return df
        return df[(df["위도"] >= min_lat) & (df["위도"] <= max_lat) & (df["경도"] >= min_lon) & (df["경도"] <= max_lon)]

    bus_filtered = filter_bounds(bus_df)
    cctv_filtered = filter_bounds(cctv_df)
    subway_filtered = filter_bounds(subway_df)

    # 버스 레이어 
    bus_group = folium.FeatureGroup(name="버스 정류장", show=False)
    for _, row in bus_filtered.iterrows():
        folium.Marker(
            location=[row["위도"], row["경도"]],
            icon=folium.Icon(color="blue", icon="bus", prefix="fa"),
            tooltip=row.get("정류장명", "버스 정류장")
        ).add_to(bus_group)
    bus_group.add_to(fmap)

    # CCTV 레이어 
    cctv_group = folium.FeatureGroup(name="CCTV", show=False)
    for _, row in cctv_filtered.iterrows():
        folium.Marker(
            location=[row["위도"], row["경도"]],
            icon=folium.Icon(color="green", icon="video", prefix="fa"),
            tooltip="방범용 CCTV"
        ).add_to(cctv_group)
    cctv_group.add_to(fmap)
    
    # 지하철 레이어
    if not subway_filtered.empty:
        subway_group = folium.FeatureGroup(name="지하철역", show=False)
        for _, row in subway_filtered.iterrows():
            folium.Marker(
                location=[row["위도"], row["경도"]],
                icon=folium.Icon(color="orange", icon="subway", prefix="fa"),
                tooltip=row.get("역명", "지하철역")
            ).add_to(subway_group)
        subway_group.add_to(fmap)


def add_heatmap(fmap: folium.Map, scored_df: pd.DataFrame) -> None:
    heat_group = folium.FeatureGroup(name="최적 자취방 히트맵", show=False)
    heat_data = scored_df[["위도", "경도", "최적점수"]].values.tolist()
    HeatMap(
        heat_data,
        name="최적 자취방 히트맵",
        min_opacity=0.35,
        radius=18,
        blur=14,
        max_zoom=14,
        show=False,
    ).add_to(fmap)


def create_map(scored_df: pd.DataFrame, bus_df: pd.DataFrame, cctv_df: pd.DataFrame, subway_df: pd.DataFrame, top_n: int, focus_lat: float = None, focus_lon: float = None) -> folium.Map:
    top_df = scored_df.head(top_n)
    
    if focus_lat is not None and focus_lon is not None:
        center_lat = float(focus_lat)
        center_lon = float(focus_lon)
        zoom_level = 16 # 
    else:
        center_lat = float(top_df["위도"].mean())
        center_lon = float(top_df["경도"].mean())
        zoom_level = 14

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_level, tiles="CartoDB positron")

    # 동의대학교 정문 마커 
    folium.Marker(
        location=[UNI_LAT, UNI_LON],
        icon=folium.Icon(color="blue", icon="star", prefix="fa"),
        tooltip="동의대학교 정문"
    ).add_to(fmap)

    add_heatmap(fmap, scored_df)
    add_top_room_markers(fmap, scored_df, top_n)
    add_reference_layers(fmap, bus_df, cctv_df, subway_df, top_df)
    
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def main() -> None:
    args = parse_args()

    house_df = load_csv(args.house_path)
    bus_df = load_csv(args.bus_path)
    cctv_df = load_csv(args.cctv_path)
    subway_df = load_csv(args.subway_path, optional=True)

    print("자취방 입지 점수 연산을 시작합니다...")
    scored_df = prepare_house_scores(
        house_df=house_df,
        bus_df=bus_df,
        cctv_df=cctv_df,
        subway_df=subway_df,
        weight_rent=args.weight_rent,
        weight_dist=args.weight_dist,
        weight_year=args.weight_year,
    )

    # 중복 건물 제거
    scored_df = scored_df.drop_duplicates(subset=["위도", "경도"], keep="first").reset_index(drop=True)

    fmap = create_map(scored_df, bus_df, cctv_df, subway_df, args.top_n)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))

    score_output_path = output_path.with_name("optimal_room_scores.csv")
    scored_df.to_csv(score_output_path, index=False, encoding="utf-8-sig")

    print("-" * 40)
    print("지도 및 데이터 생성이 완료되었습니다.")
    print(f"적용된 가중치 | 월세:{args.weight_rent}, 학교거리:{args.weight_dist}, 연식:{args.weight_year}")
    print(f"지도 저장 완료: {output_path}")
    print(f"상위 후보 수: {min(args.top_n, len(scored_df))}개 (중복 건물 제거됨)")


if __name__ == "__main__":
    main()