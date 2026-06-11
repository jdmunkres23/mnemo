# server.py
# 역할: HTTP 서버 구현. GET 요청 라우팅, 정적 파일 서빙, JSON API 엔드포인트 제공.
# 연결: src/viewer/ 정적 파일을 서빙하고, /api/* 엔드포인트로 session.json 데이터를 반환한다.
# 참고 노트북: notebooks/phase2/01_http_server.ipynb (섹션 1~3)

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

VIEWER_DIR = Path(__file__).parent / "viewer"


def _make_handler(data_dir: Path):
    """data_dir을 클로저로 캡처하는 요청 핸들러 클래스를 반환한다.

    내부 클래스에 data_dir을 주입하기 위해 팩토리 함수를 사용한다.
    HTTPServer는 핸들러 클래스(인스턴스가 아님)를 인자로 받으므로,
    클래스 변수 _data_dir 에 경로를 미리 바인딩하는 방식이다.
    (노트북 섹션 2 이론 참고)
    """
    class Handler(BaseHTTPRequestHandler):
        _data_dir = data_dir

        def log_message(self, fmt, *args):
            logger.debug(fmt, *args)

        def do_GET(self):
            # TODO (노트북 섹션 1 본 실습): urlparse로 경로를 추출한 뒤 아래 규칙으로 분기한다.
            #
            # 분기 규칙:
            #   path in ("", "/")          → _redirect("/viewer/")
            #   path in ("/viewer", "/viewer/") → _serve_file(VIEWER_DIR / "index.html")
            #   path.startswith("/viewer/")     → rel = path[len("/viewer/"):] 로 파일 경로 계산
            #                                     _serve_file(VIEWER_DIR / rel)
            #   path == "/api/sessions"         → _api_sessions()
            #   path.startswith("/api/session/")→ session_id 추출 후 _api_session(session_id)
            #   그 외                            → _not_found()
            path = urlparse(self.path).path
            if path in ("", "/"):
                self._redirect("/viewer/")
            elif path in ("/viewer", "/viewer/"):
                self._serve_file(VIEWER_DIR / "index.html")
            elif path.startswith("/viewer/"):
                rel = path[len("/viewer/"):]
                self._serve_file(VIEWER_DIR / rel)
            elif path == "/api/sessions":
                self._api_sessions()
            elif path.startswith("/api/session/"):
                self._api_session(path[len("/api/session/"):])
            else:
                self._not_found()


        def _redirect(self, location: str):
            # TODO (노트북 섹션 1 미니 실습): 301 리다이렉트 응답을 보낸다.
            # send_response(301) → send_header("Location", location) → end_headers()
            self.send_response(301)
            self.send_header("Location", location)
            self.end_headers()

        def _serve_file(self, file_path: Path):
            # TODO (노트북 섹션 3 본 실습): 파일을 읽어 MIME 타입과 함께 200 응답으로 전달한다.
            #
            # 1. file_path.read_bytes() — FileNotFoundError 시 _not_found(), 그 외 예외 시 _error(500, ...)
            # 2. mimetypes.guess_type(str(file_path)) → mime 추론, None 이면 "application/octet-stream"
            # 3. send_response(200) → Content-Type, Content-Length 헤더 → end_headers() → wfile.write(data)
            try:
                body = file_path.read_bytes()
            except FileNotFoundError:
                self._not_found()
                return # return이 없으면 아래 코드를 계속 실행하게 됨.
            except Exception:
                self._error(500, "Internal Server Error")
                return
            mime, _ = mimetypes.guess_type(str(file_path))
            if mime is None:
                mime = 'application/octet-stream'
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            

        def _api_sessions(self):
            # TODO (노트북 섹션 2 본 실습): data_dir/*.json 파일을 읽어 세션 메타데이터 목록을 반환한다.
            #
            # 반환 형식: [{ "session_id", "title", "updated_at", "turn_count" }, ...]
            # - 각 .json 파일을 파싱해서 turns가 없으면 건너뛴다
            # - updated_at 기준 내림차순 정렬 후 _json() 호출
            # - 파싱 실패 시 logger.warning으로 파일명 기록하고 건너뛴다
            sessions = []
            for file_path in self._data_dir.glob("*.json"):
                try:
                    data = json.loads(file_path.read_text(encoding='utf-8'))
                except Exception:
                    logger.warning("파싱 실패: %s", file_path.name)
                    continue
                turns = data.get("turns", [])
                if not turns:
                    continue
                sessions.append({
                    "session_id": data['session_id'],
                    "title": data['title'],
                    "updated_at": data['updated_at'],
                    "turn_count": len(turns),
                })
            sessions.sort(key=lambda s: s['updated_at'], reverse=True) # 루프 밖에 있어야 함.
            self._json(sessions)
            


        def _api_session(self, session_id: str):
            # TODO (노트북 섹션 3 본 실습): 보안 검증 후 session.json을 읽어 반환한다.
            #
            # 보안: session_id가 비어 있거나 "/", "\\", ".." 을 포함하면 _not_found()
            # 파일 없으면 _not_found()
            # 읽기 오류 시 _error(500, "Internal Server Error")
            # 성공 시: Content-Type application/json, Content-Length, 200 응답
            if not session_id or '/' in session_id or '\\' in session_id or '..' in session_id:
                self._not_found()
            else:
                file_path = self._data_dir/f"{session_id}.json"
                try:
                    body  = file_path.read_bytes() # 오류 안나는지 확인 필요
                except FileNotFoundError:
                    self._not_found()
                    return
                except Exception:
                    self._error(500, "Internal Server Error")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def _json(self, obj):
            # TODO (노트북 섹션 1 본 실습): Python 객체를 JSON으로 직렬화해 200 응답으로 전달한다.
            # json.dumps(obj, ensure_ascii=False).encode("utf-8")
            # Content-Type: application/json; charset=utf-8
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _not_found(self):
            self._error(404, "Not Found")

        def _error(self, code: int, message: str):
            # TODO (노트북 섹션 1 본 실습): 상태 코드와 메시지 본문으로 에러 응답을 보낸다.
            # body = message.encode()
            # send_response(code) → Content-Type text/plain, Content-Length → end_headers() → write
            body = message.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="AI Conversation Viewer")
    ap.add_argument("--port", type=int, default=8080, metavar="PORT",
                    help="서버 포트 (기본값: 8080)")
    ap.add_argument("--no-browser", action="store_true",
                    help="브라우저 자동 열기 비활성화")
    ap.add_argument("--data-dir", type=Path, default=Path("conversations_learning"),
                    metavar="PATH", help="세션 데이터 디렉토리 (기본값: ./conversations_learning)")
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
