# 2단계 계층적 토픽 경계 탐지 프로토타입: 거친 분류(다수결) -> 세그먼트별 세분화(다수결).
# src/ 파이프라인에는 포함되지 않음 — 검증용 수동 실험 스크립트.
#
# 사용법:
#   python scripts/debug_boundaries_hierarchical.py [model] [n_runs] [threshold] [session_file]
#   기본값: llama-3.3-70b-versatile / 5 / 0.5 / eval-long-001.session.json
#
# 1단계: boundary_v1_baseline.txt로 N번 호출 -> 인덱스별 등장 비율이 threshold 이상이면 "거친 경계"로 확정
# 2단계: 거친 경계로 나뉜 각 구간마다 boundary_v3_split_check.txt로 N번 호출 -> 역시 다수결로 세부 경계 확정
# 결과를 scripts/debug_boundaries_hierarchical_log.jsonl에 한 줄(JSON)로 저장

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = Path(__file__).parent
LOG_PATH = SCRIPT_DIR / "debug_boundaries_hierarchical_log.jsonl"
PROMPTS_DIR = SCRIPT_DIR / "prompts"
sys.path.insert(0, str(PROJECT_ROOT))

from src._groq import chat_completion, load_env_key

MODEL = sys.argv[1] if len(sys.argv) > 1 else "llama-3.3-70b-versatile"
N_RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
THRESHOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
SESSION_FILE = sys.argv[4] if len(sys.argv) > 4 else "eval-long-001.session.json"

session_path = PROJECT_ROOT / "eval_data" / SESSION_FILE
session = json.loads(session_path.read_text(encoding="utf-8"))
turns = session["turns"]

all_user_msgs = []
for i, turn in enumerate(turns):
    if turn["role"] == "user":
        text = " ".join(b["text"] for b in turn["blocks"] if b["type"] == "text")
        all_user_msgs.append((i, text))

api_key = load_env_key()
if not api_key:
    print("GROQ_API_KEY를 찾을 수 없습니다 (.env 확인 필요)")
    sys.exit(1)

print(f"모델: {MODEL} / N_RUNS: {N_RUNS} / THRESHOLD: {THRESHOLD}")
print(f"세션: {SESSION_FILE} / 사용자 turn 개수: {len(all_user_msgs)}")


def vote_boundaries(user_msgs, prompt_file, label):
    """prompt_file로 N_RUNS번 호출해 인덱스별 등장 횟수를 집계하고, threshold 넘는 것만 확정 경계로 반환."""
    prompt_template = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
    prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)
    prompt = prompt_template.replace("{{USER_MESSAGES}}", prompt_input)
    user_idxs_set = set(i for i, _ in user_msgs)

    counter = Counter()
    raw_runs = []
    for run_i in range(N_RUNS):
        content, usage, _ = chat_completion(
            [{"role": "user", "content": prompt}],
            MODEL, api_key, max_tokens=300, temperature=0.0
        )
        nums = re.findall(r"\d+", content)
        boundaries = [int(n) for n in nums]
        boundaries = [b for b in boundaries if 1 <= b <= len(turns) - 1 and b in user_idxs_set]
        for b in set(boundaries):
            counter[b] += 1
        raw_runs.append({"raw_content": content, "boundaries": boundaries, "usage": usage})
        print(f"  [{label}] run {run_i + 1}/{N_RUNS}: {boundaries}")

    confirmed = sorted(idx for idx, count in counter.items() if count / N_RUNS >= THRESHOLD)
    return confirmed, dict(counter), raw_runs


# ===== 1단계: 거친 분류 =====
print("\n===== 1단계: 거친 분류 (v1 baseline, 전체 대화) =====")
coarse_boundaries, coarse_votes, coarse_raw = vote_boundaries(
    all_user_msgs, "boundary_v1_baseline.txt", "1단계"
)
print(f"거친 경계 확정: {coarse_boundaries}")
print(f"득표: {coarse_votes}")

# ===== 2단계: 세그먼트별 세분화 =====
print("\n===== 2단계: 세그먼트별 세분화 =====")
starts = [0] + coarse_boundaries
ends = coarse_boundaries + [len(turns)]

final_boundaries = list(coarse_boundaries)
stage2_log = []

for seg_start, seg_end in zip(starts, ends):
    seg_user_msgs = [(i, t) for i, t in all_user_msgs if seg_start <= i < seg_end]
    print(f"\n-- 구간 turns[{seg_start}:{seg_end}], 사용자 메시지 {len(seg_user_msgs)}개 --")

    if len(seg_user_msgs) <= 2:
        print("  메시지 2개 이하 -> 세분화 생략")
        stage2_log.append({"segment": [seg_start, seg_end], "skipped": True})
        continue

    sub_boundaries, sub_votes, sub_raw = vote_boundaries(
        seg_user_msgs, "boundary_v3_split_check.txt", f"seg {seg_start}-{seg_end}"
    )
    print(f"  세부 경계 확정: {sub_boundaries}")
    final_boundaries.extend(sub_boundaries)
    stage2_log.append({
        "segment": [seg_start, seg_end],
        "sub_boundaries": sub_boundaries,
        "votes": sub_votes,
        "raw_runs": sub_raw,
    })

final_boundaries = sorted(set(final_boundaries))
print(f"\n===== 최종 경계 (1단계 + 2단계 병합) =====")
print(final_boundaries)
print(f"최종 토픽 개수: {len(final_boundaries) + 1}")

record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "session": SESSION_FILE,
    "model": MODEL,
    "n_runs": N_RUNS,
    "threshold": THRESHOLD,
    "stage1_coarse_boundaries": coarse_boundaries,
    "stage1_votes": coarse_votes,
    "stage1_raw_runs": coarse_raw,
    "stage2_segments": stage2_log,
    "final_boundaries": final_boundaries,
    "final_topic_count": len(final_boundaries) + 1,
}
with LOG_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\n결과를 {LOG_PATH.name}에 저장했습니다.")
