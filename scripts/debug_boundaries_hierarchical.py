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

import itertools
import json
import re
import statistics
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


def optimal_1d_partition(values, k):
    """정렬된 1차원 값을 SSE(그룹 내 편차 제곱합) 최소가 되도록 k개의 연속 구간으로 나눈다.
    1차원에서는 최적 분할이 항상 정렬 순서상 연속 구간이므로,
    절단점 k-1개의 조합을 전수조사해서 진짜 최적해를 구한다 (Lloyd's algorithm 불필요)."""
    values = sorted(values)
    n = len(values)
    if k <= 1 or n <= k:
        return [values]

    def sse(group):
        if not group:
            return 0.0
        m = statistics.mean(group)
        return sum((v - m) ** 2 for v in group)

    best_groups, best_sse = None, float("inf")
    for cuts in itertools.combinations(range(1, n), k - 1):
        bounds = (0,) + cuts + (n,)
        groups = [values[bounds[i]:bounds[i + 1]] for i in range(k)]
        total = sum(sse(g) for g in groups)
        if total < best_sse:
            best_sse, best_groups = total, groups

    return best_groups


def determine_boundaries(per_run_boundaries, n_runs, valid_idxs):
    """run별로 몇 개의 경계를 냈는지의 최빈값을 k(진짜 경계 개수)로 채택하고,
    그 최빈값이 THRESHOLD 이상의 run에서 나왔을 때만 신뢰. 이후 전체 값을 optimal_1d_partition으로
    k개 그룹으로 나누고, 각 그룹의 중앙값을 가장 가까운 유효 인덱스로 스냅해 확정 경계로 반환."""
    counts_per_run = [len(set(b)) for b in per_run_boundaries]
    count_freq = Counter(counts_per_run)
    mode_k, mode_freq = count_freq.most_common(1)[0]
    ratio = mode_freq / n_runs

    log = {"counts_per_run": counts_per_run, "mode_k": mode_k, "mode_ratio": ratio}

    if mode_k == 0 or ratio < THRESHOLD:
        log["groups"] = []
        return [], log

    pooled = [v for boundaries in per_run_boundaries for v in set(boundaries)]
    groups = optimal_1d_partition(pooled, mode_k)

    confirmed = []
    group_log = []
    for g in groups:
        if not g:
            continue
        med = statistics.median(g)
        rep = min(valid_idxs, key=lambda x: (abs(x - med), x))
        confirmed.append(rep)
        group_log.append({"values": g, "representative": rep})
    log["groups"] = group_log

    return sorted(set(confirmed)), log


def vote_boundaries(user_msgs, prompt_file, label, exclude=frozenset()):
    """prompt_file로 N_RUNS번 호출하고, determine_boundaries()로 확정 경계를 반환.
    exclude: 후보에서 제외할 인덱스 (예: 세그먼트 자기 자신의 시작 turn)."""
    prompt_template = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
    prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)
    prompt = prompt_template.replace("{{USER_MESSAGES}}", prompt_input)
    user_idxs_set = set(i for i, _ in user_msgs)
    valid_idxs = sorted(user_idxs_set - set(exclude))

    per_run_boundaries = []
    raw_runs = []
    for run_i in range(N_RUNS):
        content, usage, _ = chat_completion(
            [{"role": "user", "content": prompt}],
            MODEL, api_key, max_tokens=300, temperature=0.0
        )
        nums = re.findall(r"\d+", content)
        boundaries = [int(n) for n in nums]
        boundaries = [b for b in boundaries if 1 <= b <= len(turns) - 1 and b in user_idxs_set and b not in exclude]
        per_run_boundaries.append(boundaries)
        raw_runs.append({"raw_content": content, "boundaries": boundaries, "usage": usage})
        print(f"  [{label}] run {run_i + 1}/{N_RUNS}: {boundaries}")

    confirmed, vote_log = determine_boundaries(per_run_boundaries, N_RUNS, valid_idxs)
    return confirmed, vote_log, raw_runs


# ===== 1단계: 거친 분류 =====
print("\n===== 1단계: 거친 분류 (v1 baseline, 전체 대화) =====")
coarse_boundaries, coarse_vote_log, coarse_raw = vote_boundaries(
    all_user_msgs, "boundary_v1_baseline.txt", "1단계"
)
print(f"거친 경계 확정: {coarse_boundaries}")
print(f"투표 근거: {coarse_vote_log}")

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

    sub_boundaries, sub_vote_log, sub_raw = vote_boundaries(
        seg_user_msgs, "boundary_v3_split_check.txt", f"seg {seg_start}-{seg_end}",
        exclude={seg_start}
    )
    print(f"  세부 경계 확정: {sub_boundaries}")
    final_boundaries.extend(sub_boundaries)
    stage2_log.append({
        "segment": [seg_start, seg_end],
        "sub_boundaries": sub_boundaries,
        "vote_log": sub_vote_log,
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
    "stage1_vote_log": coarse_vote_log,
    "stage1_raw_runs": coarse_raw,
    "stage2_segments": stage2_log,
    "final_boundaries": final_boundaries,
    "final_topic_count": len(final_boundaries) + 1,
}
with LOG_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\n결과를 {LOG_PATH.name}에 저장했습니다.")
