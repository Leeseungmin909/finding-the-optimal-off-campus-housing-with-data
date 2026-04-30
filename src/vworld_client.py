from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from dotenv import load_dotenv
import requests
from requests import Response
from requests.exceptions import RequestException

try:
    from pyproj import Transformer
except ImportError:  # pragma: no cover - optional at import time
    Transformer = None
    
load_dotenv()

class VWorldAPIError(RuntimeError):
    """Raised when the VWorld API returns an error response."""


class VWorldRequestError(RuntimeError):
    """Raised when a network issue occurs while calling the VWorld API."""


def transform_coordinates(
    x: float,
    y: float,
    source_crs: str = "EPSG:4326",
    target_crs: str = "EPSG:4326",
) -> Tuple[float, float]:
    """
    Transform coordinates between CRS definitions.

    Returns a tuple in (longitude, latitude) order for consistency.
    """
    if source_crs.upper() == target_crs.upper():
        return x, y

    if Transformer is None:
        raise ImportError(
            "pyproj is required for coordinate transformation. "
            "Install dependencies with `pip install -r requirements.txt`."
        )

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat


def polygon_centroid(ring: Iterable[Iterable[float]]) -> Tuple[float, float]:
    """
    Calculate a polygon centroid from a single linear ring.
    Falls back to simple averaging if the signed area is zero.
    """
    points = [(float(x), float(y)) for x, y in ring]
    if len(points) < 3:
        raise ValueError("At least three points are required to compute a centroid.")

    if points[0] != points[-1]:
        points.append(points[0])

    signed_area = 0.0
    centroid_x = 0.0
    centroid_y = 0.0

    for i in range(len(points) - 1):
        x0, y0 = points[i]
        x1, y1 = points[i + 1]
        cross = (x0 * y1) - (x1 * y0)
        signed_area += cross
        centroid_x += (x0 + x1) * cross
        centroid_y += (y0 + y1) * cross

    signed_area *= 0.5
    if signed_area == 0:
        xs = [x for x, _ in points[:-1]]
        ys = [y for _, y in points[:-1]]
        return sum(xs) / len(xs), sum(ys) / len(ys)

    centroid_x /= 6 * signed_area
    centroid_y /= 6 * signed_area
    return centroid_x, centroid_y


@dataclass
class VWorldClient:
    api_key: str
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    base_url: str = "https://api.vworld.kr"

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self._request_with_retry(path, params)

        payload = response.json()
        response_meta = payload.get("response", {})
        status = response_meta.get("status")

        if status and status != "OK":
            message = response_meta.get("error", {}).get("text") or response_meta.get("message")
            raise VWorldAPIError(message or f"VWorld API error: {status}")

        return payload

    def _request_with_retry(self, path: str, params: Dict[str, Any]) -> Response:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response
            except RequestException as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                time.sleep(self.retry_delay * attempt)

        raise VWorldRequestError(
            f"VWorld 요청 실패: {path}, 재시도 {self.max_retries}회 모두 실패"
        ) from last_error

    def get_coordinates_from_address(
        self,
        address: str,
        address_type: str = "PARCEL",
        output_crs: str = "EPSG:4326",
    ) -> Optional[Tuple[float, float]]:
        """
        Resolve an address with the VWorld geocoder.

        Returns (longitude, latitude) or None when no match is found.
        """
        params = {
            "service": "address",
            "request": "getcoord",
            "version": "2.0",
            "crs": output_crs,
            "refine": "true",
            "simple": "false",
            "format": "json",
            "type": address_type,
            "address": address,
            "key": self.api_key,
        }
        payload = self._get("/req/address", params)
        result = payload.get("response", {}).get("result")
        if not result:
            return None

        point = result.get("point", {})
        x = point.get("x")
        y = point.get("y")
        if x is None or y is None:
            return None

        return float(x), float(y)

    def get_parcel_centroid_by_pnu(
        self,
        pnu: str,
        source_crs: str = "EPSG:4326",
        target_crs: str = "EPSG:4326",
    ) -> Optional[Tuple[float, float]]:
        """
        Fetch parcel geometry by PNU and convert it to a centroid point.

        The response shape can vary by VWorld dataset, so this method supports
        both GeoJSON-like `features` responses and nested `featureCollection`.
        """
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LP_PA_CBND_BUBUN",
            "attrFilter": f"pnu:=:{pnu}",
            "geometry": "true",
            "size": "1",
            "page": "1",
            "format": "json",
            "key": self.api_key,
        }
        payload = self._get("/req/data", params)
        response_obj = payload.get("response", {})
        result = response_obj.get("result", {})

        feature_collection = result.get("featureCollection", {})
        features = feature_collection.get("features")
        if features is None:
            features = result.get("features", [])

        if not features:
            return None

        geometry = features[0].get("geometry", {})
        coordinates = geometry.get("coordinates")
        geometry_type = geometry.get("type")
        if not geometry_type or coordinates is None:
            return None

        centroid_x, centroid_y = extract_centroid(geometry_type, coordinates)
        return transform_coordinates(
            centroid_x,
            centroid_y,
            source_crs=source_crs,
            target_crs=target_crs,
        )


def extract_centroid(geometry_type: str, coordinates: Any) -> Tuple[float, float]:
    """Extract a centroid from a GeoJSON-like geometry payload."""
    if geometry_type == "Point":
        return float(coordinates[0]), float(coordinates[1])

    if geometry_type == "MultiPoint":
        first = coordinates[0]
        return float(first[0]), float(first[1])

    if geometry_type == "Polygon":
        return polygon_centroid(coordinates[0])

    if geometry_type == "MultiPolygon":
        return polygon_centroid(coordinates[0][0])

    raise ValueError(f"Unsupported geometry type: {geometry_type}")
