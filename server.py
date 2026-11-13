"""Local-only web UI for Agent Budget Lab. Run: python server.py"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import argparse
import json
import threading
import traceback
import webbrowser
import lab
import copy
import uuid
import model_tasks
import model_experiment
from model_client import ModelClient

ROOT = Path(__file__).resolve().parent
BENCH_LOCK = threading.Lock()
JOBS = {}
JOBS_LOCK = threading.Lock()


def model_worker(job_id, params):
    def publish(result):
        with JOBS_LOCK:
            JOBS[job_id] = copy.deepcopy(result)
    try:
        model_experiment.run_batch(params, progress=publish)
    except Exception:
        traceback.print_exc()
        with JOBS_LOCK:
            JOBS[job_id].update(state="failed", error="模型实验异常中止，请查看本地服务窗口。已完成调用不会自动重试。")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def json_reply(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if not self.local_host():
            return self.json_reply({"error": "只接受本机地址。"}, 403)
        path = urlsplit(self.path).path
        if path == "/api/cases":
            return self.json_reply({"cases": lab.case_list()})
        if path == "/api/health":
            return self.json_reply({"status": "ok", "mode": "local-ui", "real_model": True})
        if path == "/api/model/status":
            try:
                return self.json_reply({"model": ModelClient().status(), "tasks": model_tasks.task_ids(), "methods": model_tasks.METHODS})
            except ValueError as exc:
                return self.json_reply({"error": str(exc)}, 400)
        if path.startswith("/api/model/jobs/"):
            with JOBS_LOCK:
                result = copy.deepcopy(JOBS.get(path.rsplit("/", 1)[-1]))
            return self.json_reply(result if result else {"error": "实验不存在"}, 200 if result else 404)
        return super().do_GET()

    def do_POST(self):
        try:
            if not self.local_host():
                return self.json_reply({"error": "只接受本机地址。"}, 403)
            if self.headers.get("Origin") and self.headers.get("Origin") != "http://" + self.headers.get("Host", ""):
                return self.json_reply({"error": "只接受本地同源请求。"}, 403)
            length = int(self.headers.get("Content-Length", 0))
            if length < 0 or length > 200000:
                return self.json_reply({"error": "请求过大。"}, 413)
            params = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(params, dict):
                raise ValueError("参数必须是 JSON 对象。")
            path = urlsplit(self.path).path
            if path == "/api/compress":
                data = lab.compress_experiment(params)
            elif path == "/api/repair":
                data = lab.run_repair(params)
            elif path == "/api/probe":
                with BENCH_LOCK:
                    data = lab.probe_experiment(params)
            elif path == "/api/model/run":
                # Browser runs are development-only. Holdout requires an explicit CLI flag.
                if params.get("allow_holdout"):
                    raise ValueError("浏览器不开放留出任务，请使用 CLI 明确启用")
                model_experiment.normalize(params)
                ModelClient()
                with JOBS_LOCK:
                    if any(j.get("state") in ("queued", "running") for j in JOBS.values()):
                        return self.json_reply({"error": "已有模型实验运行中，请等待完成。"}, 409)
                    job_id = uuid.uuid4().hex[:12]
                    JOBS[job_id] = {"state": "queued", "rows": [], "total": 0}
                threading.Thread(target=model_worker, args=(job_id, params), daemon=True).start()
                return self.json_reply({"job_id": job_id}, 202)
            else:
                return self.json_reply({"error": "未知接口"}, 404)
            return self.json_reply(data)
        except (ValueError, KeyError, TypeError) as exc:
            return self.json_reply({"error": str(exc)}, 400)
        except ImportError:
            return self.json_reply({"error": "缺少 scikit-learn。请运行 python -m pip install -r requirements.txt 后重启。"}, 503)
        except Exception:
            traceback.print_exc()
            return self.json_reply({"error": "实验运行失败，请查看启动窗口中的错误信息。"}, 500)

    def local_host(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--open", action="store_true", help="Open the local UI in your default browser")
    args = parser.parse_args()
    if args.check:
        import sklearn
        print("Ready: scikit-learn", sklearn.__version__)
        return
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Agent Budget Lab: http://127.0.0.1:{args.port}  (Ctrl+C to stop)", flush=True)
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
