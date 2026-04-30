from pathlib import Path
import pandas as pd


def get_mountain_flag(bunji):
    if pd.isna(bunji):
        return "0"
    return "1" if str(bunji).startswith("산") else "0"


BASE_DIR = Path(__file__).resolve().parent.parent

house_path = BASE_DIR / "data" / "cleaned_HOUSE.csv"
region_path = BASE_DIR / "data" / "cleaned_region_code_active.csv"
output_path = BASE_DIR / "data" / "house_with_pnu.csv"
unmatched_path = BASE_DIR / "data" / "pnu_unmatched.csv"

house_df = pd.read_csv(house_path, encoding="utf-8-sig")
region_df = pd.read_csv(region_path, encoding="utf-8-sig")

print("house columns:", house_df.columns.tolist())
print("region columns:", region_df.columns.tolist())


# -----------------------------
# 1. house 데이터 정리
# -----------------------------
house_df["시도"] = house_df["시도"].astype(str).str.strip()
house_df["구"] = house_df["구"].astype(str).str.strip()
house_df["법정동"] = house_df["법정동"].astype(str).str.strip()
house_df["번지"] = house_df["번지"].astype(str).str.strip()

house_df["산여부"] = house_df["번지"].apply(get_mountain_flag)
house_df["본번"] = house_df["본번"].fillna(0).astype(int).astype(str).str.zfill(4)
house_df["부번"] = house_df["부번"].fillna(0).astype(int).astype(str).str.zfill(4)


# -----------------------------
# 2. region 데이터 정리
# -----------------------------
region_df = region_df[["법정동코드", "법정동명"]].copy()

parts = region_df["법정동명"].astype(str).str.split()

region_df["시도"] = parts.str[0].str.strip()
region_df["구"] = parts.str[1].str.strip()
region_df["법정동"] = parts.str[-1].str.strip()

region_df["법정동코드"] = region_df["법정동코드"].astype(str).str.zfill(10)


# -----------------------------
# 3. 주소 -> 법정동코드 lookup dict 생성
# -----------------------------
code_map = {
    (row["시도"], row["구"], row["법정동"]): row["법정동코드"]
    for _, row in region_df.iterrows()
}


# -----------------------------
# 4. cleaned_HOUSE 각 행의 주소를 법정동코드로 변환
# -----------------------------
house_df["법정동코드"] = house_df.apply(
    lambda row: code_map.get((row["시도"], row["구"], row["법정동"])),
    axis=1
)


# -----------------------------
# 5. PNU 생성
# -----------------------------
house_df["PNU"] = pd.NA

valid_mask = house_df["법정동코드"].notna()

house_df.loc[valid_mask, "PNU"] = (
    house_df.loc[valid_mask, "법정동코드"].astype(str).str.zfill(10)
    + house_df.loc[valid_mask, "산여부"]
    + house_df.loc[valid_mask, "본번"]
    + house_df.loc[valid_mask, "부번"]
)


# -----------------------------
# 6. 매핑 실패 확인
# -----------------------------
unmatched_df = house_df[house_df["법정동코드"].isna()].copy()

print("매핑 실패 건수:", len(unmatched_df))

if len(unmatched_df) > 0:
    print("매핑 실패 예시:")
    print(unmatched_df[["시도", "구", "법정동", "번지"]].drop_duplicates().head(20))
    unmatched_df.to_csv(unmatched_path, index=False, encoding="utf-8-sig")
    print(f"매핑 실패 파일 저장 완료: {unmatched_path}")


# -----------------------------
# 7. 결과 저장
# -----------------------------
house_df.to_csv(output_path, index=False, encoding="utf-8-sig")
print(f"PNU 생성 완료: {output_path}")

print(
    house_df[
        ["시군구", "법정동", "번지", "본번", "부번", "산여부", "법정동코드", "PNU"]
    ].head(20)
)