"""Read-only HTTP server for report viewers and calculated report JSON."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, unquote, urlsplit

from reporting.intent_reports import compare_runs, refresh_history
from reporting.response_reports import result_history


REPORT_NAMES = frozenset({"summary.json", "details.json", "runs.json", "result-summary.json",
                          "result-runs.json", "result-details.json"})
PUBLIC_FILES = frozenset({"summary.html", "runs.html", "details.html", "result_summary.html",
                          "result_runs.html", "result_details.html", "favicon.svg"})


class ReportHTTPServer(ThreadingHTTPServer):
    """Serve only report UI assets and the configured results directory."""

    daemon_threads = True

    def __init__(self, address, directory: Path, *, results_directory: Path | None = None):
        self.directory = directory.resolve()
        self.templates_directory = (self.directory / "templates").resolve()
        self.results_directory = (results_directory or self.directory / "results").resolve()
        self.report_lock = Lock()
        self.report_cache = {}
        super().__init__(address, partial(ReportRequestHandler, directory=str(self.templates_directory)))


class ReportRequestHandler(SimpleHTTPRequestHandler):
    server: ReportHTTPServer

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()

    def _send_bytes(self, body: bytes, content_type: str, *, head_only=False, cache_control="no-store"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve_health(self, *, head_only=False):
        if urlsplit(self.path).path != "/healthz":
            return False
        self._send_bytes(b'{"status":"ok"}\n', "application/json; charset=utf-8", head_only=head_only)
        return True

    def _serve_public_file(self, *, head_only=False):
        path = unquote(urlsplit(self.path).path)
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/templates/summary.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        parts = Path(path).parts
        if len(parts) != 3 or parts[1] != "templates" or parts[2] not in PUBLIC_FILES:
            return False
        target = (self.server.templates_directory / parts[2]).resolve()
        if target.parent != self.server.templates_directory or not target.is_file():
            self.send_error(404, "Not found")
            return True
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "image/svg+xml":
            content_type += "; charset=utf-8"
        self._send_bytes(target.read_bytes(), content_type, head_only=head_only,
                         cache_control="public, max-age=300")
        return True

    @staticmethod
    def _report_signature(folder: Path):
        if not folder.is_dir():
            return ()
        signature = []
        for path in folder.glob("*/details.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            signature.append((path.parent.name, stat.st_mtime_ns, stat.st_size))
        return tuple(sorted(signature))

    def _serve_raw_run_details(self, parts, *, head_only=False):
        if len(parts) != 4 or parts[1] != "results" or parts[3] != "details.json":
            return False
        run_id = parts[2]
        if run_id in ("", ".", "..") or "/" in run_id or "\\" in run_id:
            self.send_error(404, "Not found")
            return True
        target = (self.server.results_directory / run_id / "details.json").resolve()
        if target.parent.parent != self.server.results_directory or not target.is_file():
            self.send_error(404, "Not found")
            return True
        self._send_bytes(target.read_bytes(), "application/json; charset=utf-8", head_only=head_only)
        return True

    def _serve_current_report(self, *, head_only=False):
        parts = Path(unquote(urlsplit(self.path).path)).parts
        if len(parts) != 3 or parts[1] != "results" or parts[-1] not in REPORT_NAMES:
            return False
        folder = self.server.results_directory
        query = parse_qs(urlsplit(self.path).query)
        label_key = query.get("label_key", ["intent"])[0]
        if label_key not in ("intent", "policy_intent"):
            self.send_error(400, "Unknown label_key")
            return True
        include_incomplete = query.get("complete_only", ["0"])[0] != "1"
        report_name = parts[-1]
        cache_key = (report_name, label_key, include_incomplete, self._report_signature(folder))
        with self.server.report_lock:
            body = self.server.report_cache.get(cache_key)
            if body is None:
                try:
                    if report_name.startswith("result-"):
                        summary, details = result_history(folder, include_incomplete=include_incomplete,
                                                          per_run=report_name == "result-runs.json")
                        report = details if report_name == "result-details.json" else summary
                    elif report_name == "runs.json":
                        report = compare_runs(folder, label_key, include_incomplete=include_incomplete)
                    else:
                        summary, details = refresh_history(folder, label_key,
                                                           include_incomplete=include_incomplete)
                        report = summary if report_name == "summary.json" else details
                    body = (json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    self.send_error(503, "Cannot calculate reports", str(exc))
                    return True
                current_signature = cache_key[-1]
                self.server.report_cache = {
                    key: value for key, value in self.server.report_cache.items()
                    if key[-1] == current_signature
                }
                self.server.report_cache[cache_key] = body
        self._send_bytes(body, "application/json; charset=utf-8", head_only=head_only)
        return True

    def _dispatch(self, *, head_only=False):
        if (self._serve_health(head_only=head_only)
                or self._serve_public_file(head_only=head_only)
                or self._serve_current_report(head_only=head_only)):
            return
        parts = Path(unquote(urlsplit(self.path).path)).parts
        if self._serve_raw_run_details(parts, head_only=head_only):
            return
        self.send_error(404, "Not found")

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch(head_only=True)

    def do_POST(self):
        self.send_error(405, "Read-only report service")
