"""Static viewers with report JSON calculated on request, without writing files."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, unquote, urlsplit

from reporting.intent_reports import compare_runs, refresh_history
from reporting.response_reports import result_history


class ReportHTTPServer(ThreadingHTTPServer):
    def __init__(self, address, directory: Path):
        self.directory = directory.resolve()
        self.report_lock = Lock()
        super().__init__(address, partial(ReportRequestHandler, directory=str(self.directory)))


class ReportRequestHandler(SimpleHTTPRequestHandler):
    server: ReportHTTPServer

    def _serve_current_report(self, *, head_only=False):
        parts = Path(unquote(urlsplit(self.path).path)).parts
        # Aggregate paths are virtual JSON endpoints. Timestamped raw JSON is
        # served as originally recorded, without rewriting source files.
        if len(parts) != 3 or parts[-1] not in ("summary.json", "details.json", "runs.json",
                                                "result-summary.json", "result-runs.json", "result-details.json"):
            return False
        folder = self.server.directory / parts[1]
        if folder.resolve().parent != self.server.directory:
            return False
        query = parse_qs(urlsplit(self.path).query)
        label_key = query.get("label_key", ["intent"])[0]
        if label_key not in ("intent", "policy_intent"):
            self.send_error(400, "Unknown label_key")
            return True
        with self.server.report_lock:
            try:
                include_incomplete = query.get("complete_only", ["0"])[0] != "1"
                if parts[-1].startswith("result-"):
                    summary, details = result_history(folder, include_incomplete=include_incomplete,
                                                      per_run=parts[-1] == "result-runs.json")
                    report = details if parts[-1] == "result-details.json" else summary
                elif parts[-1] == "runs.json":
                    report = compare_runs(folder, label_key, include_incomplete=include_incomplete)
                else:
                    summary, details = refresh_history(folder, label_key, include_incomplete=include_incomplete)
                    report = summary if parts[-1] == "summary.json" else details
                body = (json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.send_error(503, "Cannot calculate reports", str(exc))
                return True
        # Always return fresh report bytes, even with conditional request headers.
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)
        return True

    def do_GET(self):
        if not self._serve_current_report():
            super().do_GET()

    def do_HEAD(self):
        if not self._serve_current_report(head_only=True):
            super().do_HEAD()
