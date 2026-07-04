# 70b와 scout를 번갈아(interleaved) 호출해서, 같은 시간대 서버 조건에서
# "모델 자체의 문제"와 "그 순간 서버 혼잡도"를 분리해 비교하는 진단 스크립트.
# 각 모델을 한 번씩 번갈아 부르므로, 두 모델이 거의 동일한 시간대의 서버 상태를 겪는다.
# src/ 파이프라인에는 포함되지 않음.
#
# 사용법:
#   python scripts/debug_model_interleave.py [n_each] [session_file]
#   기본값: 8 / eval-long-001.session.json

import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = Path(__file__).parent
LOG_PATH = SCRIPT_DIR / "debug_model_interleave_log.jsonl"
PROMPTS_DIR = SCRIPT_DIR / "prompts"
sys.path.insert(0, str(PROJECT_ROOT))

from src._groq import chat_completion, load_env_key

N_EACH = int(sys.argv[1]) if len(sys.argv) > 1 else 8
SESSION_FILE = sys.argv[2] if len(sys.argv) > 2 else "eval-long-001.session.json"
MODELS = ["llama-3.3-70b-versatile", "meta-llama/llama-4-scout-17b-16e-instruct"]

session_path = PROJECT_ROOT / "eval_data" / SESSION_FILE
session = json.loads(session_path.read_text(encoding="utf-8"))
turns = session["turns"]

user_msgs = []
for i, turn in enumerate(turns):
    if turn["role"] == "user":
        text = " ".join(b["text"] for b in turn["blocks"] if b["type"] == "text")
        user_msgs.append((i, text))
user_idxs_set = set(i for i, _ in user_msgs)

prompt_template = (PROMPTS_DIR / "boundary_v1_baseline.txt").read_text(encoding="utf-8")
prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)
prompt = prompt_template.replace("{{USER_MESSAGES}}", prompt_input)

api_key = load_env_key()
if not api_key:
    print("GROQ_API_KEY를 찾을 수 없습니다 (.env 확인 필요)")
    sys.exit(1)

print(f"세션: {SESSION_FILE} / 모델당 {N_EACH}회, 번갈아 호출")

results = {m: [] for m in MODELS}

for round_i in range(N_EACH):
    for model in MODELS:
        content, usage, _ = chat_completion(
            [{"role": "user", "content": prompt}],
            model, api_key, max_tokens=300, temperature=0.0
        )
        nums = re.findall(r"\d+", content)
        boundaries = [int(n) for n in nums]
        boundaries = [b for b in boundaries if 1 <= b <= len(turns) - 1 and b in user_idxs_set]
        entry = {"boundaries": boundaries, "queue_time": usage["queue_time"], "raw_content": content}
        results[model].append(entry)
        print(f"  round {round_i + 1}/{N_EACH} [{model}]: {boundaries}  (queue_time={usage['queue_time']:.4f})")

print("\n===== 요약 =====")
summary = {}
for model in MODELS:
    entries = results[model]
    boundary_tuples = [tuple(e["boundaries"]) for e in entries]
    mode_tuple, mode_count = Counter(boundary_tuples).most_common(1)[0]
    queue_times = [e["queue_time"] for e in entries]
    summary[model] = {
        "mode_boundaries": list(mode_tuple),
        "mode_match_ratio": mode_count / N_EACH,
        "avg_queue_time": statistics.mean(queue_times),
        "median_queue_time": statistics.median(queue_times),
        "max_queue_time": max(queue_times),
    }
    print(f"\n[{model}]")
    print(f"  최빈 결과: {list(mode_tuple)} ({mode_count}/{N_EACH} = {mode_count/N_EACH:.0%})")
    print(f"  queue_time: 평균 {statistics.mean(queue_times):.4f} / 중앙값 {statistics.median(queue_times):.4f} / 최대 {max(queue_times):.4f}")

record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "session": SESSION_FILE,
    "n_each": N_EACH,
    "results": results,
    "summary": summary,
}
with LOG_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\n결과를 {LOG_PATH.name}에 저장했습니다.")
