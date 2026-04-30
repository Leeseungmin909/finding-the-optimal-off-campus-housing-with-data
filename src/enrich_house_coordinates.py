from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from vworld_client import VWorldAPIError, VWorldClient, VWorldRequestError


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = BASE_DIR / "data" / "house_with_pnu.csv"
DEFAULT_OUTPUT = BASE_DIR / "data" / "house_with_coordinates.csv"
DEFAULT_DEBUG_OUTPUT = BASE_DIR / "data" / "house_with_coordinates_debug.csv"
ENV_PATH = BASE_DIR / ".env"


def build_parcel_address(row: pd.Series) -> str:
    bunji = str(row["번지"]).strip()
    return f'{str(row["시도"]).strip()} {str(row["구"]).strip()} {str(row["법정동"]).strip()} {bunji}'


def resolve_single_location(
    pnu: object,
    parcel_address: str,
    client: VWorldClient,
    query_strategy: str,
    sleep_seconds: float,
) -> tuple[object, object, object, object]:
    lon = None
    lat = None
    source = None
    error_message = None

    should_try_pnu_first = query_strategy == "pnu_then_address"
    should_try_address = query_strategy in {"pnu_then_address", "address_only"}

    if should_try_pnu_first and pd.notna(pnu):
        try:
            result = client.get_parcel_centroid_by_pnu(str(pnu))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if result:
                lon, lat = result
                source = "pnu_centroid"
                error_message = None
        except (VWorldAPIError, VWorldRequestError, ValueError) as exc:
            error_message = str(exc)

    if (lon is None or lat is None) and should_try_address:
        try:
            result = client.get_coordinates_from_address(
                parcel_address,
                address_type="PARCEL",
            )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if result:
                lon, lat = result
                source = "parcel_address"
                error_message = None
        except (VWorldAPIError, VWorldRequestError) as exc:
            if error_message is None:
                error_message = str(exc)

    return lon, lat, source, error_message


def enrich_coordinates(
    df: pd.DataFrame,
    client: VWorldClient,
    sleep_seconds: float = 0.0,
    query_strategy: str = "address_only",
) -> pd.DataFrame:
    result_df = df.copy()
    result_df["지번주소"] = result_df.apply(build_parcel_address, axis=1)

    lookup_df = (
        result_df[["PNU", "지번주소"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    resolved_lon = []
    resolved_lat = []
    resolved_source = []
    resolved_error = []
    total = len(lookup_df)

    for idx, row in lookup_df.iterrows():
        lon, lat, source, error_message = resolve_single_location(
            pnu=row.get("PNU"),
            parcel_address=row["지번주소"],
            client=client,
            query_strategy=query_strategy,
            sleep_seconds=sleep_seconds,
        )
        resolved_lon.append(lon)
        resolved_lat.append(lat)
        resolved_source.append(source)
        resolved_error.append(error_message)

        progress = idx + 1
        if progress % 100 == 0 or progress == total:
            print(f"[{progress}/{total}] 고유 주소 좌표 조회 진행 중")

    lookup_df["경도"] = resolved_lon
    lookup_df["위도"] = resolved_lat
    lookup_df["좌표조회방식"] = resolved_source
    lookup_df["좌표조회에러"] = resolved_error

    merged_df = result_df.drop(columns=["경도", "위도", "좌표조회방식", "좌표조회에러"], errors="ignore")
    merged_df = merged_df.merge(lookup_df, on=["PNU", "지번주소"], how="left")
    return merged_df.drop(columns=["지번주소"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VWorld API로 자취방 데이터에 위도/경도 좌표를 추가합니다."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help="입력 CSV 경로",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="최종 분석용 출력 CSV 경로",
    )
    parser.add_argument(
        "--debug-output",
        default=str(DEFAULT_DEBUG_OUTPUT),
        help="디버그용 출력 CSV 경로",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("VWORLD_API_KEY"),
        help="VWorld API 인증키. 기본값은 VWORLD_API_KEY 환경변수입니다.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="각 API 요청 timeout(초)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="요청 실패 시 재시도 횟수",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.1,
        help="요청 간 대기 시간(초). 과도한 연속 호출을 줄일 때 사용",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="테스트용으로 앞에서부터 일부 행만 처리",
    )
    parser.add_argument(
        "--query-strategy",
        choices=["address_only", "pnu_then_address"],
        default="address_only",
        help="좌표 조회 전략. 속도를 위해 기본값은 address_only입니다.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ENV_PATH)
    args = parse_args()

    if not args.api_key:
        raise ValueError(
            "VWorld API 키가 없습니다. `--api-key` 옵션 또는 "
            "`VWORLD_API_KEY` 환경변수를 설정해주세요."
        )

    house_df = pd.read_csv(args.input, encoding="utf-8-sig")
    if args.limit is not None:
        house_df = house_df.head(args.limit).copy()

    client = VWorldClient(
        api_key=args.api_key,
        timeout=args.timeout,
        max_retries=args.max_retries,
    )
    output_df = enrich_coordinates(
        house_df,
        client,
        sleep_seconds=args.sleep_seconds,
        query_strategy=args.query_strategy,
    )
    output_df.to_csv(args.debug_output, index=False, encoding="utf-8-sig")

    final_df = output_df.drop(columns=["좌표조회에러"], errors="ignore")
    final_df.to_csv(args.output, index=False, encoding="utf-8-sig")

    success_count = final_df["위도"].notna().sum()
    print(f"좌표 조회 완료: {success_count}/{len(final_df)}건")
    print(f"최종본 저장 경로: {args.output}")
    print(f"디버그본 저장 경로: {args.debug_output}")


if __name__ == "__main__":
    main()
