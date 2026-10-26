from __future__ import annotations

import csv
import io
import os
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse, unquote
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_file, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
USER_AGENT = "FreePDFDownloader/1.0 (local personal-use crawler)"
REQUEST_TIMEOUT = 20
MAX_FILE_BYTES = 250 * 1024 * 1024
DEFAULT_DELAY = 0.6

app = Flask(__name__, static_folder="static")
lock = threading.RLock()
state = {
    "scan_id": None, "scanning": False, "downloading": False,
    "pages_seen": 0, "page_limit": 200, "depth_limit": 3,
    "queue_count": 0, "message": "Ready", "error": None,
    "start_url": None, "results": [], "download_progress": 0,
    "download_total": 0, "download_message": ""
}
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def normalized_url(raw: str, base: str | None = None) -> str | None:
    if not raw:
        return None
    url = urljoin(base or "", raw.strip())
    url, _ = urldefrag(url)
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    return url


def same_host(url: str, host: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() == host.lower()
    except ValueError:
        return False


def safe_filename(name: str) -> str:
    name = unquote(name or "").replace("\\", "_").replace("/", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name).strip(" .")
    return (name[:180] or "document.pdf")


def filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    name = safe_filename(name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def get_robots_parser(base_url: str) -> RobotFileParser | None:
    robots_url = urljoin(base_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = session.get(robots_url, timeout=REQUEST_TIMEOUT)
        if response.status_code >= 400:
            return None
        parser.parse(response.text.splitlines())
        return parser
    except requests.RequestException:
        return None


def allowed_by_robots(parser: RobotFileParser | None, url: str) -> bool:
    if parser is None:
        return True
    try:
        return parser.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def pdf_result(url: str, source: str, size: int | None = None) -> dict:
    return {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, url).hex,
        "url": url, "source": source, "filename": filename_from_url(url),
        "size": size, "status": "Found", "selected": True
    }


def sitemap_urls(base_url: str, host: str, robots: RobotFileParser | None) -> list[str]:
    candidates = [urljoin(base_url, "/sitemap.xml"), urljoin(base_url, "/sitemap_index.xml")]
    if robots:
        try:
            candidates.extend(robots.site_maps() or [])
        except Exception:
            pass
    found: list[str] = []
    visited: set[str] = set()
    while candidates and len(visited) < 20:
        sitemap = candidates.pop(0)
        if sitemap in visited or not same_host(sitemap, host) or not allowed_by_robots(robots, sitemap):
            continue
        visited.add(sitemap)
        try:
            response = session.get(sitemap, timeout=REQUEST_TIMEOUT)
            if response.status_code >= 400 or len(response.content) > 10_000_000:
                continue
            root = ET.fromstring(response.content)
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
                    continue
                loc = normalized_url(node.text.strip(), sitemap)
                if not loc:
                    continue
                if loc.lower().split("?", 1)[0].endswith(".xml") and same_host(loc, host):
                    candidates.append(loc)
                elif loc.lower().split("?", 1)[0].endswith(".pdf"):
                    found.append(loc)
        except (requests.RequestException, ET.ParseError, ValueError):
            continue
        time.sleep(DEFAULT_DELAY)
    return found


def run_scan(start_url: str, depth_limit: int, page_limit: int):
    try:
        parsed = urlparse(start_url)
        host = parsed.hostname or ""
        robots = get_robots_parser(start_url)
        queue = deque([(start_url, 0)])
        queued = {start_url}
        visited: set[str] = set()
        results: dict[str, dict] = {}

        for url in sitemap_urls(start_url, host, robots):
            results[url] = pdf_result(url, start_url)

        while queue and len(visited) < page_limit:
            url, depth = queue.popleft()
            if url in visited or not allowed_by_robots(robots, url):
                continue
            visited.add(url)
            with lock:
                state["pages_seen"] = len(visited)
                state["queue_count"] = len(queue)
                state["message"] = f"Scanning page {len(visited)} of up to {page_limit}"
            try:
                response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if response.status_code >= 400:
                    continue
                content_type = response.headers.get("Content-Type", "").lower()
                if "html" not in content_type and not response.text.lstrip().lower().startswith(("<!doctype html", "<html")):
                    continue
                soup = BeautifulSoup(response.text, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    target = normalized_url(anchor.get("href"), response.url)
                    if not target:
                        continue
                    path_lower = urlparse(target).path.lower()
                    if path_lower.endswith(".pdf"):
                        results.setdefault(target, pdf_result(target, response.url))
                    elif depth < depth_limit and same_host(target, host) and target not in queued and target not in visited:
                        if urlparse(target).scheme in ("http", "https"):
                            queued.add(target)
                            queue.append((target, depth + 1))
                time.sleep(DEFAULT_DELAY)
            except (requests.RequestException, ValueError):
                continue

        with lock:
            state["results"] = sorted(results.values(), key=lambda x: x["filename"].lower())
            state["scanning"] = False
            state["queue_count"] = len(queue)
            state["message"] = f"Scan complete. Found {len(results)} PDF link(s) across {len(visited)} page(s)."
    except Exception as exc:
        with lock:
            state["scanning"] = False
            state["error"] = str(exc)
            state["message"] = "Scan failed."


def run_download(urls: list[str]):
    completed = 0
    total = len(urls)
    with lock:
        state["download_total"] = total
        state["download_progress"] = 0
        state["download_message"] = "Starting downloads"
    for url in urls:
        result_id = uuid.uuid5(uuid.NAMESPACE_URL, url).hex
        target_result = None
        with lock:
            target_result = next((r for r in state["results"] if r["id"] == result_id), None)
        if target_result is None:
            completed += 1
            continue
        try:
            response = None
            for attempt in range(3):
                try:
                    response = session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
                    if response.status_code in (429, 500, 502, 503, 504):
                        response.close()
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(1.5 * (attempt + 1))
            if response is None:
                raise RuntimeError("No response")
            content_type = response.headers.get("Content-Type", "").lower()
            if "pdf" not in content_type and not urlparse(url).path.lower().endswith(".pdf"):
                # Validate the file signature rather than saving an HTML error page.
                pass
            filename = safe_filename(target_result["filename"])
            destination = DOWNLOAD_DIR / filename
            stem, suffix = destination.stem, destination.suffix
            counter = 1
            while destination.exists():
                destination = DOWNLOAD_DIR / f"{stem}_{counter}{suffix}"
                counter += 1
            bytes_written = 0
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    bytes_written += len(chunk)
                    if bytes_written > MAX_FILE_BYTES:
                        raise RuntimeError("File exceeded 250 MB safety limit")
                    handle.write(chunk)
            response.close()
            with destination.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    destination.unlink(missing_ok=True)
                    raise RuntimeError("URL did not return a valid PDF file")
            with lock:
                target_result["status"] = "Downloaded"
                target_result["downloaded_as"] = destination.name
                target_result["size"] = bytes_written
        except Exception as exc:
            with lock:
                target_result["status"] = "Failed"
                target_result["error"] = str(exc)[:240]
        completed += 1
        with lock:
            state["download_progress"] = completed
            state["download_message"] = f"Processed {completed} of {total} file(s)"
    with lock:
        state["downloading"] = False
        state["download_message"] = f"Download run complete: processed {completed} file(s)."


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/status")
def status():
    with lock:
        return jsonify({k: v for k, v in state.items() if k != "results"} | {"results": state["results"]})


@app.post("/api/scan")
def start_scan():
    payload = request.get_json(silent=True) or {}
    url = normalized_url(payload.get("url", ""))
    if not url:
        return jsonify({"error": "Enter a valid http or https website URL."}), 400
    depth = max(0, min(int(payload.get("depth", 3)), 8))
    page_limit = max(1, min(int(payload.get("page_limit", 200)), 5000))
    with lock:
        if state["scanning"] or state["downloading"]:
            return jsonify({"error": "A scan or download is already running."}), 409
        state.update({
            "scan_id": uuid.uuid4().hex, "scanning": True, "pages_seen": 0,
            "page_limit": page_limit, "depth_limit": depth, "queue_count": 1,
            "message": "Starting scan", "error": None, "start_url": url,
            "results": [], "download_progress": 0, "download_total": 0
        })
    threading.Thread(target=run_scan, args=(url, depth, page_limit), daemon=True).start()
    return jsonify({"ok": True, "message": "Scan started"}), 202


@app.post("/api/download")
def start_download():
    payload = request.get_json(silent=True) or {}
    urls = payload.get("urls", [])
    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "Select at least one PDF."}), 400
    with lock:
        if state["scanning"] or state["downloading"]:
            return jsonify({"error": "A scan or download is already running."}), 409
        known = {r["url"] for r in state["results"]}
        urls = list(dict.fromkeys(u for u in urls if isinstance(u, str) and u in known))
        if not urls:
            return jsonify({"error": "No selected URLs match the scan results."}), 400
        state["downloading"] = True
    threading.Thread(target=run_download, args=(urls,), daemon=True).start()
    return jsonify({"ok": True, "message": f"Downloading {len(urls)} PDF(s)"}), 202


@app.get("/api/export.csv")
def export_csv():
    with lock:
        rows = list(state["results"])
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["filename", "url", "source", "size", "status", "downloaded_as", "error"])
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    data.seek(0)
    return send_file(data, mimetype="text/csv", as_attachment=True, download_name="pdf-discovery.csv")


@app.get("/api/downloads")
def list_downloads():
    files = []
    for path in sorted(DOWNLOAD_DIR.glob("*.pdf")):
        try:
            files.append({"filename": path.name, "size": path.stat().st_size})
        except OSError:
            pass
    return jsonify(files)


if __name__ == "__main__":
    print("FreePDFDownloader is starting at http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=False, threaded=True)
