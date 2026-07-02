# usage_tracker.py
# 역할: Groq API 사용량 기록 + 분당 토큰 한도 초과 시 자동 대기
# 연결: _groq.py chat_completion 성공 시 자동 호출

from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_USAGE_DIR = Path(__file__).parent.parent / "usage"

# 페이지 파싱 실패 시 폴백용 기본값
_TPD_DEFAULTS: dict[str, int] = {
    "llama-3.3-70b-versatile":                   100_000,
    "llama-3.1-8b-instant":                      500_000,
    "openai/gpt-oss-120b":                       200_000,
    "openai/gpt-oss-20b":                        200_000,
    "meta-llama/llama-4-scout-17b-16e-instruct": 500_000,
    "qwen/qwen3-32b":                            500_000,
    "qwen/qwen3.6-27b":                          200_000,
}

_tpd_cache: dict[str, int] | None = None


# ── 한도 테이블 ──────────────────────────────────────────────────────────────

def _parse_k_value(s: str) -> int:
    """'100K' → 100000, '500K' → 500000, '—' → 0"""
    s = s.strip().replace(",", "").replace(" ", "")
    if not s or s in ("—", "-", "No limit", "Nolimit"):
        return 0
    if s.endswith("K"):
        return int(float(s[:-1]) * 1_000)
    if s.endswith("M"):
        return int(float(s[:-1]) * 1_000_000)
    try:
        return int(s)
    except ValueError:
        return 0


def _parse_tpd_from_html(html: str) -> dict[str, int]:
    """HTML에서 모델별 TPD 파싱. 실패 시 빈 dict 반환."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    # 모델명 패턴: llama-*, qwen/*, openai/*, meta-llama/*, groq/*, allam-*
    pattern = re.compile(
        r'((?:llama|qwen|openai|meta-llama|groq|allam|canopy)[\w\-./]+)'
        r'\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)'
    )
    result = {}
    for m in pattern.finditer(text):
        model = m.group(1)
        tpd   = _parse_k_value(m.group(5))   # 5번째 컬럼 = TPD
        if tpd > 0:
            result[model] = tpd
    return result


_LIMITS_FILE = _USAGE_DIR / "limits.json"


def _fetch_tpd_limits() -> dict[str, int]:
    """오늘(UTC) 한도 테이블 반환. 당일 캐시 있으면 재사용, 없으면 페이지에서 파싱."""
    global _tpd_cache
    if _tpd_cache is not None:
        return _tpd_cache

    today = _utc_today()
    _USAGE_DIR.mkdir(exist_ok=True)

    # 당일 캐시 파일이 있으면 바로 사용
    if _LIMITS_FILE.exists():
        cached = json.loads(_LIMITS_FILE.read_text(encoding="utf-8"))
        if cached.get("date") == today:
            _tpd_cache = cached["limits"]
            return _tpd_cache

    # 없거나 날짜가 다르면 페이지에서 파싱
    try:
        req = urllib.request.Request(
            "https://console.groq.com/docs/rate-limits",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
        parsed = _parse_tpd_from_html(html)
        if len(parsed) >= 3:
            _LIMITS_FILE.write_text(
                json.dumps({"date": today, "limits": parsed}, ensure_ascii=False),
                encoding="utf-8"
            )
            _tpd_cache = parsed
            print(f"  [usage] 한도 테이블 업데이트: {len(parsed)}개 모델")
            return _tpd_cache
    except Exception:
        pass

    print("  [usage] 한도 테이블 조회 실패 → 기본값 사용")
    _tpd_cache = _TPD_DEFAULTS.copy()
    return _tpd_cache


# ── UTC 기준 날짜별 파일 관리 ─────────────────────────────────────────────────

def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_usage_file() -> Path:
    """오늘(UTC) 파일 경로 반환. 날짜가 바뀌었으면 이전 파일 삭제."""
    _USAGE_DIR.mkdir(exist_ok=True)
    today = _utc_today()
    today_file = _USAGE_DIR / f"{today}.jsonl"
    for f in _USAGE_DIR.glob("*.jsonl"):
        if f.stem != today:
            f.unlink()
    return today_file


# ── 핵심 기능 ─────────────────────────────────────────────────────────────────

def record(model: str, usage: dict) -> None:
    """호출 결과를 오늘(UTC) 파일에 한 줄 추가."""
    entry = {
        "time":              datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "model":             model,
        "prompt_tokens":     usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens":      usage.get("total_tokens", 0),
    }
    with _get_usage_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_today_usage(model: str) -> int:
    """오늘(UTC) 해당 모델의 누적 total_tokens 반환."""
    f = _get_usage_file()
    if not f.exists():
        return 0
    total = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["model"] == model:
            total += entry["total_tokens"]
    return total


def get_daily_remaining(model: str) -> int:
    """오늘(UTC) 해당 모델의 남은 일일 토큰 수 반환."""
    limit = _fetch_tpd_limits().get(model, 100_000)
    return max(0, limit - get_today_usage(model))


def parse_reset_seconds(reset_str: str) -> float:
    """'1m26.4s' → 86.4, '185ms' → 0.185, '30s' → 30.0"""
    if not reset_str:
        return 0.0
    total = 0.0
    m = re.search(r'(\d+)m', reset_str)
    if m:
        total += int(m.group(1)) * 60
    ms = re.search(r'([\d.]+)ms', reset_str)
    if ms:
        total += float(ms.group(1)) / 1000
    else:
        s = re.search(r'([\d.]+)s', reset_str)
        if s:
            total += float(s.group(1))
    return total


def throttle_if_needed(rate_limit: dict) -> None:
    """분당 남은 토큰이 한도의 25% 미만이면 리셋까지 대기."""
    remaining = int(rate_limit.get("remaining_tokens") or 0)
    limit     = int(rate_limit.get("limit_tokens")     or 12_000)
    reset_str = rate_limit.get("reset_tokens", "")

    if remaining < max(int(limit * 0.25), 2_000):
        wait = parse_reset_seconds(reset_str) + 0.5
        if wait > 0:
            print(f"  [usage] 분당 토큰 부족 ({remaining}/{limit}) → {wait:.1f}초 대기...")
            time.sleep(wait)
