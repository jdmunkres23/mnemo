# detect_topic_boundaries() 후보 프롬프트/모델의 응답 안정성을 비교하는 수동 진단 도구.
# src/ 파이프라인에는 포함되지 않음 — 필요할 때 사람이 직접 실행.
# 실행할 때마다 결과를 debug_boundaries_log.jsonl에 한 줄씩 append 저장한다 (모델·프롬프트별 비교용).
#
# 사용법:
#   python scripts/debug_boundaries.py [model] [prompt_file] [session_file]
#   기본값: llama-3.1-8b-instant / boundary_v1_baseline.txt / eval-long-001.session.json
#
# 새 프롬프트를 실험하려면 scripts/prompts/ 에 {{USER_MESSAGES}} 플레이스홀더가 들어간
# .txt 파일을 추가하고 두 번째 인자로 파일명을 넘기면 된다.

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT_DIR = Path(__file__).parent
LOG_PATH = SCRIPT_DIR / "debug_boundaries_log.jsonl"
PROMPTS_DIR = SCRIPT_DIR / "prompts"
sys.path.insert(0, str(PROJECT_ROOT))

from src._groq import chat_completion, load_env_key

MODEL = sys.argv[1] if len(sys.argv) > 1 else "llama-3.1-8b-instant"
PROMPT_FILE = sys.argv[2] if len(sys.argv) > 2 else "boundary_v1_baseline.txt"
SESSION_FILE = sys.argv[3] if len(sys.argv) > 3 else "eval-long-001.session.json"

session_path = PROJECT_ROOT / "eval_data" / SESSION_FILE
session = json.loads(session_path.read_text(encoding="utf-8"))

# detect_topic_boundaries()와 동일한 방식으로 사용자 turn 추출
turns = session["turns"]
user_msgs = []
for i, turn in enumerate(turns):
    if turn["role"] == "user":
        text = " ".join(b["text"] for b in turn["blocks"] if b["type"] == "text")
        user_msgs.append((i, text))

print(f"모델: {MODEL}")
print(f"프롬프트 파일: {PROMPT_FILE}")
print(f"세션: {SESSION_FILE}")
print(f"사용자 turn 개수: {len(user_msgs)}")

prompt_input = "\n".join(f"{i}: {text}" for i, text in user_msgs)
prompt_template = (PROMPTS_DIR / PROMPT_FILE).read_text(encoding="utf-8")
prompt = prompt_template.replace("{{USER_MESSAGES}}", prompt_input)

print("\n===== 프롬프트 길이 (문자 수) =====")
print(len(prompt))

api_key = load_env_key()
if not api_key:
    print("GROQ_API_KEY를 찾을 수 없습니다 (.env 확인 필요)")
    sys.exit(1)

content, usage, _ = chat_completion(
    [{"role": "user", "content": prompt}],
    MODEL, api_key, max_tokens=300, temperature=0.0
)

print("\n===== RAW content (파싱 전) =====")
print(repr(content))

print("\n===== usage =====")
print(usage)

nums = re.findall(r"\d+", content)
print("\n===== re.findall(r'\\d+', content) 결과 =====")
print(nums)

user_idxs_set = set(i for i, _ in user_msgs)
boundaries = [int(n) for n in nums]
boundaries = [b for b in boundaries if 1 <= b <= len(turns) - 1 and b in user_idxs_set]
print("\n===== 최종 필터링된 boundaries =====")
print(boundaries)
print(f"토픽 개수: {len(boundaries) + 1}")

record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "session": SESSION_FILE,
    "model": MODEL,
    "prompt_file": PROMPT_FILE,
    "raw_content": content,
    "parsed_nums": nums,
    "boundaries": boundaries,
    "topic_count": len(boundaries) + 1,
    "usage": usage,
}
with LOG_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

print(f"\n결과를 {LOG_PATH.name}에 저장했습니다.")
