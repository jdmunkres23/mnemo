# _groq.py
# 역할: Groq API 래퍼. urllib 기반으로 chat completion과 모델 목록 조회를 제공한다.
# 연결: server.py /api/groq-proxy, /api/groq-models 에서 호출
#       evaluator.py 에서도 직접 호출한다.
# 참고 노트북: notebooks/phase3/01_groq_api_notebook.md

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
import os

_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODELS_URL = "https://api.groq.com/openai/v1/models"
# Cloudflare가 기본 Python UA를 봇으로 차단 (error 1010) → 브라우저 UA 위장
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def load_env_key() -> str:
    """Read GROQ_API_KEY from .env file or environment. (노트북 섹션 1 참고)

    .env 파일 형식: GROQ_API_KEY=gsk_...  (# 주석 줄 제외)
    파일 없으면 os.environ["GROQ_API_KEY"] 시도.
    둘 다 없으면 빈 문자열 반환.
    """
    env = Path("../.env")
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                return line[len("GROQ_API_KEY="):].strip().strip('"').strip("'")
    return os.environ.get("GROQ_API_KEY", "")


def extract_wait_seconds(error_msg: str, default: float = 60.0) -> float:
    m = re.search(r"try again in ([\d.]+)s", error_msg)
    return float(m.group(1)) if m else default


def chat_completion(
    messages: list[dict],
    model: str,
    api_key: str,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> tuple[str, dict, dict]:
    """Groq chat completions API 호출. (노트북 섹션 1, 2, 3 참고)

    Returns: (content, usage_dict, rate_limit_dict)
    Raises: ValueError on API error

    rate_limit_dict 키: remaining_requests, remaining_tokens,
                        reset_requests, reset_tokens

    구현 순서:
    1. payload JSON 직렬화 → bytes
    2. urllib.request.Request 생성 (Authorization Bearer + Content-Type + User-Agent)
    3. 최대 4회 재시도 루프:
       - urlopen(req, timeout=60) 으로 호출
       - 응답 헤더에서 rate_limit 파싱
       - HTTPError 429 → 메시지에서 대기 시간 파싱 후 time.sleep → 재시도
       - 그 외 HTTPError → ValueError로 변환 raise
    4. body["choices"][0]["message"]["content"] 추출
    5. (content, usage, rate_limit) 반환
    """
    # 1. payload JSON 직렬화
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }).encode('utf-8')

    # 2. urllib.request.Request 생성
    req = urllib.request.Request(
        _CHAT_URL,
        data = payload,
        headers = {"Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": _UA,
        },
        method='POST'
    )

    # 3. 최대 4회 재시도 루프
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                rate_limit_dict = {
                    "remaining_requests": resp.headers.get("x-ratelimit-remaining-requests", ""),
                    "remaining_tokens": resp.headers.get("x-ratelimit-remaining-tokens", ""),
                    "reset_requests": resp.headers.get("x-ratelimit-reset-requests", ""),
                    "reset_tokens": resp.headers.get("x-ratelimit-reset-tokens", "")
                }
                body = json.loads(resp.read().decode("utf-8"))
                content = body['choices'][0]['message']['content']
                usage = body['usage']
                return (content, usage, rate_limit_dict)

        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read().decode('utf-8'))
            error_msg = body['error']['message']
            if exc.code == 429 and attempt < 3:
                wait = extract_wait_seconds(error_msg) + 2.0
                time.sleep(wait)
                continue
            else:
                raise ValueError(error_msg)





def list_models(api_key: str) -> list[dict]:
    """Groq 가용 모델 목록을 id 순으로 반환. (노트북 섹션 1 참고)

    Returns: [{"id": str, "context_window": int}, ...]
    제외 조건: "whisper" 포함 (오디오), "guard" 포함 (안전 분류)
    Raises: ValueError on API error

    구현 순서:
    1. GET _MODELS_URL + Authorization + User-Agent 헤더
    2. body["data"] 에서 각 모델의 id, context_window 추출
    3. "whisper", "guard" 포함 모델 제외
    4. id 기준 정렬 후 반환
    """
    req = urllib.request.Request(
        _MODELS_URL,
        headers={
            "Authorization": f'Bearer {api_key}',
            "User-Agent": _UA,
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            models = [{"id": m["id"], "context_window": m["context_window"]} for m in body["data"]]
            models = [m for m in models if "whisper" not in m["id"] and "guard" not in m["id"]]
            models = sorted(models, key=lambda m: m["id"])
            return models
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode('utf-8'))
        raise ValueError(body['error']['message'])

