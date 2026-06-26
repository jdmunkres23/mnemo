from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse

from src._groq import chat_completion, list_models, load_env_key

logger = logging.getLogger(__name__)

VIEWER_DIR = Path(__file__).parent / "viewer"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_handler(data_dir: Path):
    chats_dir = data_dir / "chats"

    class Handler(BaseHTTPRequestHandler):
        _data_dir = data_dir
        _chats_dir = chats_dir

        def log_message(self, fmt, *args):
            logger.debug(fmt, *args)

        # ── GET ──────────────────────────────────────────────────────────────

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)

            if path in ("", "/"):
                self._redirect("/viewer/")
                return

            if path in ("/viewer", "/viewer/"):
                self._serve_file(VIEWER_DIR / "index.html")
                return

            if path.startswith("/viewer/"):
                rel = path[len("/viewer/"):]
                self._serve_file(VIEWER_DIR / rel)
                return

            if path == "/api/sessions":
                self._api_sessions()
                return

            if path.startswith("/api/session/"):
                session_id = path[len("/api/session/"):]
                self._api_session(session_id)
                return

            if path == "/api/chat-list":
                session_id = params.get("session_id", [None])[0]
                self._api_chat_list(session_id)
                return

            if path == "/api/chat-load":
                chat_id = params.get("id", [None])[0]
                self._api_chat_load(chat_id)
                return

            if path == "/api/groq-key-status":
                self._api_groq_key_status()
                return

            if path == "/api/groq-models":
                api_key = params.get("api_key", [None])[0] or load_env_key()
                self._api_groq_models(api_key)
                return

            self._not_found()

        # ── POST ─────────────────────────────────────────────────────────────

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            body = self._read_body()

            if path == "/api/groq-proxy":
                self._api_groq_proxy(body)
                return

            if path == "/api/index-session":
                self._api_index_session(body)
                return

            if path == "/api/query-semantic":
                self._api_query_semantic(body)
                return

            if path == "/api/chat-save":
                self._api_chat_save(body)
                return

            self._not_found()

        # ── DELETE ───────────────────────────────────────────────────────────

        def do_DELETE(self):
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)

            if path == "/api/chat-delete":
                chat_id = params.get("id", [None])[0]
                self._api_chat_delete(chat_id)
                return

            self._not_found()

        # ── helpers ──────────────────────────────────────────────────────────

        def _read_body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (ValueError, TypeError):
                length = 0
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def _redirect(self, location: str):
            self.send_response(301)
            self.send_header("Location", location)
            self.end_headers()

        def _serve_file(self, file_path: Path):
            try:
                data = file_path.read_bytes()
            except FileNotFoundError:
                self._not_found()
                return
            except Exception as exc:
                logger.warning("Error serving %s: %s", file_path, exc)
                self._error(500, "Internal Server Error")
                return

            mime, _ = mimetypes.guess_type(str(file_path))
            mime = mime or "application/octet-stream"
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, status: int = 200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _not_found(self):
            self._error(404, "Not Found")

        def _error(self, code: int, message: str):
            body = message.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # ── API handlers ─────────────────────────────────────────────────────

        def _api_sessions(self):
            sessions = []
            for p in self._data_dir.glob("*.json"):
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    turns = raw.get("turns", [])
                    if not turns:
                        continue
                    has_text = any(
                        b.get("text", "").strip()
                        for t in turns
                        for b in t.get("blocks", [])
                        if b.get("type") == "text"
                    )
                    if not has_text:
                        continue
                    sessions.append({
                        "session_id": raw["session_id"],
                        "title": raw.get("title") or raw["session_id"],
                        "updated_at": raw.get("updated_at", ""),
                        "turn_count": len(turns),
                        "has_branches": bool(raw.get("branches")),
                    })
                except Exception:
                    logger.warning("Skipping invalid session file: %s", p.name)

            sessions.sort(key=lambda s: s["updated_at"], reverse=True)
            self._json(sessions)

        def _api_session(self, session_id: str):
            if not session_id or "/" in session_id or "\\" in session_id or ".." in session_id:
                self._not_found()
                return

            file_path = self._data_dir / f"{session_id}.json"
            if not file_path.exists():
                self._not_found()
                return

            try:
                data = file_path.read_bytes()
            except Exception as exc:
                logger.warning("Error reading session %s: %s", session_id, exc)
                self._error(500, "Internal Server Error")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _api_groq_proxy(self, body: dict):
            messages = body.get("messages")
            model = body.get("model", "llama-3.1-8b-instant")
            api_key = body.get("api_key", "").strip() or load_env_key()
            max_tokens = int(body.get("max_tokens", 2048))
            temperature = float(body.get("temperature", 0.7))

            if not messages:
                self._json({"error": "messages is required"}, 400)
                return
            if not api_key:
                self._json({"error": "Groq API 키가 없습니다. 설정 패널에서 입력하거나 .env에 GROQ_API_KEY를 추가하세요."}, 400)
                return

            try:
                content, usage, rate_limit = chat_completion(
                    messages, model, api_key,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except ValueError as exc:
                self._json({"error": str(exc)}, 502)
                return
            except Exception as exc:
                logger.warning("Groq proxy error: %s", exc)
                self._json({"error": "Groq API 호출 실패"}, 502)
                return

            self._json({"content": content, "usage": usage, "rate_limit": rate_limit})

        def _api_chat_list(self, session_id: str | None):
            if not session_id:
                self._json([])
                return

            chats = []
            if self._chats_dir.exists():
                for p in self._chats_dir.glob("*.json"):
                    try:
                        raw = json.loads(p.read_text(encoding="utf-8"))
                        if raw.get("session_id") != session_id:
                            continue
                        chats.append({
                            "id": raw["id"],
                            "title": raw.get("title", "AI 채팅"),
                            "updated_at": raw.get("updated_at", ""),
                            "message_count": len(raw.get("messages", [])),
                        })
                    except Exception:
                        pass

            chats.sort(key=lambda c: c["updated_at"], reverse=True)
            self._json(chats)

        def _api_chat_load(self, chat_id: str | None):
            if not chat_id or "/" in chat_id or "\\" in chat_id or ".." in chat_id:
                self._not_found()
                return

            file_path = self._chats_dir / f"{chat_id}.json"
            if not file_path.exists():
                self._not_found()
                return

            try:
                data = file_path.read_bytes()
            except Exception:
                self._error(500, "Internal Server Error")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _api_chat_save(self, body: dict):
            session_id = body.get("session_id", "")
            messages = body.get("messages", [])
            title = body.get("title", "AI 채팅")
            chat_id = body.get("id") or str(uuid.uuid4())

            self._chats_dir.mkdir(parents=True, exist_ok=True)
            file_path = self._chats_dir / f"{chat_id}.json"

            created_at = _now_iso()
            if file_path.exists():
                try:
                    existing = json.loads(file_path.read_text(encoding="utf-8"))
                    created_at = existing.get("created_at", created_at)
                except Exception:
                    pass

            record = {
                "id": chat_id,
                "session_id": session_id,
                "title": title,
                "messages": messages,
                "created_at": created_at,
                "updated_at": _now_iso(),
            }
            file_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._json({"id": chat_id})

        def _api_groq_key_status(self):
            has_key = bool(load_env_key())
            self._json({"has_server_key": has_key})

        def _api_groq_models(self, api_key: str):
            if not api_key:
                self._json({"error": "api_key is required"}, 400)
                return
            try:
                models = list_models(api_key)
                self._json({"models": models})
            except ValueError as exc:
                self._json({"error": str(exc)}, 502)
            except Exception as exc:
                logger.warning("groq-models error: %s", exc)
                self._json({"error": "모델 목록 조회 실패"}, 502)

        def _api_index_session(self, body: dict):
            session_id = body.get("session_id", "")
            if not session_id or "/" in session_id or ".." in session_id:
                self._json({"error": "invalid session_id"}, 400)
                return

            session_path = self._data_dir / f"{session_id}.json"
            if not session_path.exists():
                self._json({"error": "세션을 찾을 수 없습니다"}, 404)
                return

            try:
                from src.indexer import build_index
                session = json.loads(session_path.read_text(encoding="utf-8"))
                session_dir = self._data_dir / session_id
                build_index(session, session_dir)
                self._json({"ok": True})
            except Exception as exc:
                logger.warning("index-session error: %s", exc)
                self._json({"error": "인덱싱 실패"}, 500)

        def _api_query_semantic(self, body: dict):
            session_id = body.get("session_id", "")
            query = body.get("query", "")
            top_k = int(body.get("top_k", 3))

            if not session_id or not query:
                self._json({"error": "session_id and query are required"}, 400)
                return
            if "/" in session_id or ".." in session_id:
                self._json({"error": "invalid session_id"}, 400)
                return

            session_path = self._data_dir / f"{session_id}.json"
            if not session_path.exists():
                self._json({"error": "세션을 찾을 수 없습니다"}, 404)
                return

            try:
                from src.indexer import build_index, search
                session = json.loads(session_path.read_text(encoding="utf-8"))
                session_dir = self._data_dir / session_id
                index_path = build_index(session, session_dir)
                results = search(query, index_path, top_k)
                self._json(results)
            except Exception as exc:
                logger.warning("query-semantic error: %s", exc)
                self._json({"error": "검색 실패"}, 500)

        def _api_chat_delete(self, chat_id: str | None):
            if not chat_id or "/" in chat_id or "\\" in chat_id or ".." in chat_id:
                self._not_found()
                return

            file_path = self._chats_dir / f"{chat_id}.json"
            if not file_path.exists():
                self._not_found()
                return

            try:
                file_path.unlink()
            except Exception:
                self._error(500, "Internal Server Error")
                return

            self._json({"ok": True})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Conversation Viewer")
    ap.add_argument("--port", type=int, default=8080, metavar="PORT",
                    help="서버 포트 (기본값: 8080)")
    ap.add_argument("--no-browser", action="store_true",
                    help="브라우저 자동 열기 비활성화")
    ap.add_argument("--data-dir", type=Path, default=Path("conversations"),
                    metavar="PATH", help="세션 데이터 디렉토리 (기본값: ./conversations)")
    args = ap.parse_args()

    if not args.data_dir.exists():
        print(f"오류: 데이터 디렉토리를 찾을 수 없습니다: {args.data_dir}")
        print("먼저 'python -m parser --input <conversations.json>'을 실행하세요.")
        raise SystemExit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    handler = _make_handler(args.data_dir)
    server = HTTPServer(("", args.port), handler)

    url = f"http://localhost:{args.port}/viewer/"
    print(f"뷰어 주소: {url}")
    print(f"데이터 경로: {args.data_dir.resolve()}")
    print("종료하려면 Ctrl+C를 누르세요.")

    if not args.no_browser:
        Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버가 중지되었습니다.")


if __name__ == "__main__":
    main()
