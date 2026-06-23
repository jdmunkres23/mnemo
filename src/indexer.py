# indexer.py
# 역할: 세션 텍스트를 고정 크기 청크로 분할, fastembed로 임베딩, 코사인 유사도 검색.
# 연결: server.py의 POST /api/index-session, POST /api/query-semantic
# 참고 노트북: notebooks/phase3/02_embedding.ipynb (섹션 1~3)
#              notebooks/phase3/03_baseline_rag.ipynb (섹션 1~2)

from __future__ import annotations
import json
import math
from pathlib import Path

EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
CHUNK_SIZE = 2000  # 기본 청크 크기 (글자 수)

_model = None  # 지연 초기화 (첫 embed 호출 시)


def _get_model():
    """fastembed TextEmbedding 인스턴스 반환 (싱글턴)."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """텍스트 목록을 벡터 목록으로 변환한다. (노트북 02 섹션 1 참고)

    반환: [[float, ...], ...] — 각 텍스트의 1024차원 벡터
    """
    # list(model.embed(texts)) → numpy array 리스트 → 각 원소를 list()로 변환
    return list(_get_model().embed(texts))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 반환한다. (노트북 02 섹션 2 참고)

    반환: -1.0 ~ 1.0 (norm이 0이면 0.0)
    """
    # dot(a, b) / (norm(a) * norm(b))
    dot = sum(ai * bi for ai, bi in zip(a,b))
    norm_a = math.sqrt(sum(ai**2 for ai in a))
    norm_b = math.sqrt(sum(bi**2 for bi in b))
    if norm_a != 0 and norm_b != 0:
        return dot / (norm_a * norm_b)
    else:
        return 0.0

def format_turn(turn: dict) -> str | None:
    """turn 하나에서 text 블록을 추출해 "[사용자]\n텍스트" 형식으로 반환한다.
    
    text 블록이 없으면 None 반환.
    여러 text 블록은 줄바꿈으로 합친다.
    
    힌트:
    - role_label = "사용자" if turn["role"] == "user" else "AI"
    - b["type"] == "text" 인 블록만 필터링
    - f"[{role_label}]\n{text}"
    """
    # TODO
    role_label = "사용자" if turn['role'] == 'user' else "AI"
    text = "\n".join(b['text'] for b in turn['blocks'] if b ['type'] == 'text')
    if text:
        return f'[{role_label}]\n{text}'
    else:
        return None

def chunk_session(session: dict, chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """session.json의 turns를 고정 크기 청크로 분할한다. (노트북 02 섹션 3 참고)

    반환: [{"text": str, "turn_start": int, "turn_end": int}, ...]
    분할: turns를 [사용자]/[AI] 포맷으로 이어붙이다 chunk_size 초과 시 새 청크.
    text 블록만 포함 (thinking, tool_use 등 제외).
    chunk_size=0 이면 전체를 단일 청크로.
    """
    _SEP = "\n\n---\n\n"
    # 1. turns 순회 → text 블록만 추출 → "[사용자]\n텍스트" 또는 "[AI]\n텍스트"
    # 2. parts 누적, chunk_size 초과 시 현재 parts 저장 후 새 청크 시작
    # 3. 청크가 비어있으면 크기 초과해도 일단 추가 (빈 청크 방지)
    # 4. 루프 끝에 마지막 청크 저장
    chunks = []
    parts = []
    turn_start = 0
    current_len = 0

    for i, turn in enumerate(session['turns']):
        text = format_turn(turn)
        added_len = len(text) + (len(_SEP) if parts else 0)
        if parts and chunk_size!= 0 and current_len + added_len > chunk_size:
            chunks.append({
                'text': _SEP.join(parts),
                'turn_start': turn_start,
                'turn_end': i
            })
            current_len = 0
            turn_start = i
            parts = []
        parts.append(text)
        current_len += added_len

    if parts:
        chunks.append({
            'text': _SEP.join(parts),
            'turn_start': turn_start,
            'turn_end': len(session['turns']) - 1
        })

    return chunks



def build_index(session: dict, session_dir: Path, chunk_size: int = CHUNK_SIZE) -> Path:
    """세션을 청크로 분할 후 임베딩해 session_index.json으로 저장한다. (노트북 03 섹션 1 참고)

    저장 경로: session_dir / "session_index.json"
    저장 형식: [{"text": str, "embedding": list[float], "turn_start": int, "turn_end": int}, ...]
    반환: session_index.json 경로
    인덱스가 이미 존재하면 재계산 없이 경로만 반환.
    """
    # 1. index_path = session_dir / "session_index.json"
    # 2. index_path.exists() → 바로 반환
    # 3. session_dir.mkdir(parents=True, exist_ok=True)
    # 4. chunk_session(session, chunk_size) → chunks
    # 5. embed_texts([c["text"] for c in chunks]) → embeddings
    # 6. 각 chunk에 embedding 추가 → json 저장
    pass  # TODO


def search(query: str, index_path: Path, top_k: int = 3) -> list[dict]:
    """코사인 유사도로 상위 top_k 청크를 검색한다. (노트북 03 섹션 2 참고)

    반환: [{"text": str, "score": float, "turn_start": int, "turn_end": int}, ...]
          유사도 내림차순 정렬.
    인덱스 파일이 없으면 [] 반환.
    """
    # 1. index_path 없으면 [] 반환
    # 2. 인덱스 로드
    # 3. embed_texts([query])[0] → query_vec
    # 4. 각 청크와 cosine_similarity 계산 → score 추가
    # 5. score 내림차순 정렬 → [:top_k] 반환
    pass  # TODO
