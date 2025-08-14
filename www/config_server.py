import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs


DATA_DIR = os.path.join(os.getcwd(), "data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def _load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _atomic_write_json(path, data):
    dir_name = os.path.dirname(path)
    temp_path = os.path.join(dir_name, "__settings.tmp")
    with open(temp_path, 'w') as tf:
        json.dump(data, tf, indent=2)
    os.replace(temp_path, path)


def _extract_id(token: str):
    token = token.strip()
    m = re.match(r"^<@&(?P<id>\d+)>$", token)
    if m:
        return int(m.group("id"))
    if token.isdigit():
        return int(token)
    return None


def _parse_id_list(csv_text: str):
    if not csv_text:
        return []
    ids = []
    for part in csv_text.split(','):
        maybe = _extract_id(part)
        if maybe is not None:
            ids.append(maybe)
    return ids


class ConfigHandler(BaseHTTPRequestHandler):
    server_version = "ECTiersConfig/1.0"

    def _send_html(self, body: str, status: int = 200):
        body_bytes = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_json(self, obj, status: int = 200):
        payload = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/settings":
            self._send_json(_load_settings())
            return

        settings = _load_settings()
        page = f"""
<!doctype html>
<html>
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>ECTiers Configuration</title>
    <style>
      :root {{
        --bg: #0f1220; --card: #171a2b; --text: #e7e7f0; --muted: #9aa0b4; --accent: #7c5cff;
        --ok: #2ecc71; --warn: #f39c12; --err: #e74c3c; --border: #2a2f45;
      }}
      * {{ box-sizing: border-box; }}
      body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif; background: var(--bg); color: var(--text); }}
      header {{ padding: 16px 24px; border-bottom: 1px solid var(--border); display:flex; align-items:center; gap:12px; }}
      header h1 {{ font-size: 18px; margin:0; }}
      main {{ max-width: 860px; margin: 24px auto; padding: 0 16px 48px; }}
      .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
      .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
      label {{ display:block; font-weight:600; margin: 10px 0 6px; color: var(--muted); }}
      input, textarea {{ width: 100%; padding: 10px 12px; background: #0e1020; color: var(--text); border: 1px solid var(--border); border-radius: 8px; outline: none; }}
      input:focus, textarea:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgba(124, 92, 255, .15); }}
      .row {{ display:flex; gap: 12px; align-items: center; }}
      .hint {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
      .actions {{ margin-top: 18px; display:flex; gap:12px; align-items:center; }}
      button {{ background: var(--accent); color: white; border: 0; border-radius: 8px; padding: 10px 16px; font-weight: 600; cursor: pointer; }}
      .json {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; white-space: pre-wrap; background:#0e1020; border:1px solid var(--border); border-radius:10px; padding:12px; }}
      footer {{ opacity:.6; text-align:center; margin-top: 24px; }}
    </style>
  </head>
  <body>
    <header>
      <h1>ECTiers Configuration</h1>
      <span class=\"hint\">Local admin panel</span>
    </header>
    <main>
      <form class=\"card\" method=\"POST\" action=\"/save\">        
        <div class=\"grid\">
          <div>
            <label for=\"results_channel\">Results channel ID</label>
            <input id=\"results_channel\" name=\"results_channel\" placeholder=\"123456789012345678\" value=\"{settings.get('results_channel','')}\" />
            <div class=\"hint\">Discord text channel ID to post results in.</div>
          </div>
          <div>
            <label for=\"results_roles\">Results roles (IDs or mentions, comma-separated)</label>
            <input id=\"results_roles\" name=\"results_roles\" placeholder=\"<@&111>, 222, 333\" value=\"{','.join(str(x) for x in settings.get('results_roles', []) )}\" />
            <div class=\"hint\">Only members with at least one of these roles can run /results.</div>
          </div>
          <div>
            <label for=\"queue_role\">Queue tester role (ID or mention)</label>
            <input id=\"queue_role\" name=\"queue_role\" placeholder=\"<@&111111> or 111111\" value=\"{settings.get('queue_role','')}\" />
            <div class=\"hint\">Members with this role can Join/Leave the tester queue.</div>
          </div>
          <div>
            <label for=\"queue_category\">Queue category ID</label>
            <input id=\"queue_category\" name=\"queue_category\" placeholder=\"123456789012345678\" value=\"{settings.get('queue_category','')}\" />
            <div class=\"hint\">Category channel where related tickets/threads may be created.</div>
          </div>
          <div>
            <label for=\"staff_role\">Staff role (optional, ID or mention)</label>
            <input id=\"staff_role\" name=\"staff_role\" placeholder=\"<@&444444> or 444444\" value=\"{settings.get('staff_role','')}\" />
            <div class=\"hint\">Optional role used by some queue operations.</div>
          </div>
        </div>
        <div class=\"actions\">
          <button type=\"submit\">Save settings</button>
          <span class=\"hint\">Settings are written to data/settings.json instantly.</span>
        </div>
      </form>

      <div class=\"card\" style=\"margin-top:16px;\">
        <div class=\"row\" style=\"justify-content: space-between;\">
          <strong>Current raw settings</strong>
        </div>
        <pre class=\"json\">{json.dumps(settings, indent=2)}</pre>
        <div class=\"hint\">Endpoint: <code>/api/settings</code></div>
      </div>

      <footer>ECTiers • Local configuration panel</footer>
    </main>
  </body>
</html>
"""
        self._send_html(page)

    def do_POST(self):
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get('Content-Length', '0'))
        data = self.rfile.read(length).decode('utf-8')
        form = parse_qs(data)

        def _get(name):
            values = form.get(name)
            return values[0] if values else ''

        existing = _load_settings()
        next_settings = dict(existing)

        # results_channel
        rc = _get('results_channel').strip()
        if rc:
            rc_id = _extract_id(rc)
            if rc_id is not None:
                next_settings['results_channel'] = rc_id
        # results_roles
        rr = _get('results_roles')
        next_settings['results_roles'] = _parse_id_list(rr)
        # queue_role
        qr = _get('queue_role').strip()
        if qr:
            qr_id = _extract_id(qr)
            if qr_id is not None:
                next_settings['queue_role'] = qr_id
        # queue_category
        qc = _get('queue_category').strip()
        if qc:
            qc_id = _extract_id(qc)
            if qc_id is not None:
                next_settings['queue_category'] = qc_id
        # staff_role (optional)
        sr = _get('staff_role').strip()
        if sr:
            sr_id = _extract_id(sr)
            if sr_id is not None:
                next_settings['staff_role'] = sr_id

        os.makedirs(DATA_DIR, exist_ok=True)
        _atomic_write_json(SETTINGS_PATH, next_settings)

        # After saving, redirect back home
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()


def start_config_server(host: str = "127.0.0.1", port: int = 8765):
    server = HTTPServer((host, port), ConfigHandler)

    def _run():
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    thread = threading.Thread(target=_run, name=f"ConfigServer:{host}:{port}", daemon=True)
    thread.start()
    return thread


