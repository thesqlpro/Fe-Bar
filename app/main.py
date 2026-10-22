"""Parker Hannifin Component Predictive Maintenance Intelligence App.

Flask app that embeds the AI/BI dashboard via iframe and provides
a custom Genie chat interface for Parker aerospace component maintenance,
powered by the Databricks SDK.
"""
import os, json, traceback
from flask import Flask, render_template_string, request, jsonify
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import MessageStatus

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WORKSPACE_URL = "https://fevm-genie-zeroops-mfg.cloud.databricks.com"
WORKSPACE_ID  = "7474652206075893"
DASHBOARD_ID  = "01f1a5f8872c151b939582bfede572d6"
GENIE_SPACE   = "01f1a5f87b0b17719e85516055a09440"

DASHBOARD_EMBED = f"{WORKSPACE_URL}/embed/dashboardsv3/{DASHBOARD_ID}/published?o={WORKSPACE_ID}"

# Maintenance manual search (Vector Search delta-sync index over parsed manual tasks)
MANUALS_INDEX = os.getenv("MANUALS_INDEX", "genie_zeroops_mfg_catalog.default.maintenance_manual_index")
MANUAL_COLS = ["chunk_id", "aircraft_type", "engine", "ata_chapter", "task_title", "fault_code", "system",
               "part_name", "part_number", "related_parts", "symptoms", "probable_causes", "limits",
               "corrective_steps", "torque_values", "manual_name"]
_facets_cache = {}

app = Flask(__name__)
w   = WorkspaceClient()          # uses app service-principal creds

# ---------------------------------------------------------------------------
# Genie API helpers
# ---------------------------------------------------------------------------
def genie_ask(question: str, conversation_id: str | None = None):
    """Send a question to the Genie space, return dict with answer."""
    try:
        if conversation_id:
            msg = w.genie.create_message_and_wait(
                space_id=GENIE_SPACE,
                conversation_id=conversation_id,
                content=question,
            )
        else:
            msg = w.genie.start_conversation_and_wait(
                space_id=GENIE_SPACE,
                content=question,
            )

        reply_text = msg.content or ""
        sql_query  = None
        table_data = None

        # Extract SQL + results from attachments
        for att in (msg.attachments or []):
            if att.query and att.query.query:
                sql_query = att.query.query
            if att.text:
                if hasattr(att.text, 'content'):
                    reply_text = att.text.content or reply_text

        # Fetch query results — execute then poll until SUCCEEDED
        import time as _t
        for att in (msg.attachments or []):
            aid = getattr(att, 'attachment_id', None) or getattr(att, 'id', None)
            if att.query and aid:
                try:
                    qr = w.genie.execute_message_attachment_query(
                        space_id=GENIE_SPACE,
                        conversation_id=msg.conversation_id,
                        message_id=msg.message_id,
                        attachment_id=aid,
                    )
                    # Poll until query completes (up to 30s)
                    for _ in range(30):
                        state = str(qr.statement_response.status.state) if qr.statement_response and qr.statement_response.status else ""
                        if "PENDING" not in state and "RUNNING" not in state:
                            break
                        _t.sleep(1)
                        qr = w.genie.get_message_attachment_query_result(
                            space_id=GENIE_SPACE,
                            conversation_id=msg.conversation_id,
                            message_id=msg.message_id,
                            attachment_id=aid,
                        )
                    if qr.statement_response and qr.statement_response.result:
                        result = qr.statement_response.result
                        cols = []
                        col_types = []
                        if qr.statement_response.manifest and qr.statement_response.manifest.schema:
                            for c in (qr.statement_response.manifest.schema.columns or []):
                                cols.append(c.name)
                                col_types.append(str(c.type_name) if c.type_name else "STRING")
                        rows = []
                        if result.data_array:
                            rows = result.data_array[:100]
                        table_data = {"columns": cols, "types": col_types, "rows": rows}
                        break  # got results, stop looping attachments
                except Exception:
                    pass

        return {
            "ok": True,
            "text": reply_text,
            "sql": sql_query,
            "table": table_data,
            "conversation_id": msg.conversation_id,
            "status": str(msg.status),
        }
    except Exception as e:
        return {"ok": False, "text": f"Error: {e}", "sql": None, "table": None,
                "conversation_id": conversation_id, "status": "FAILED"}


# ---------------------------------------------------------------------------
# Maintenance manual search helpers
# ---------------------------------------------------------------------------
def manuals_query(text: str, filters: dict | None = None, k: int = 8, query_type: str = "HYBRID"):
    """Query the manual index; returns a list of dicts (one per manual task) incl. 'score'."""
    kwargs = dict(index_name=MANUALS_INDEX, columns=MANUAL_COLS, query_text=text,
                  num_results=k, query_type=query_type)
    if filters:
        kwargs["filters_json"] = json.dumps(filters)
    res = w.vector_search_indexes.query_index(**kwargs)
    cols = [c.name for c in (res.manifest.columns or [])]
    return [dict(zip(cols, row)) for row in ((res.result.data_array if res.result else None) or [])]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template_string(PAGE_HTML, dashboard_url=DASHBOARD_EMBED,
                                 workspace_url=WORKSPACE_URL,
                                 genie_space_id=GENIE_SPACE)

@app.route("/api/genie", methods=["POST"])
def api_genie():
    body = request.get_json(force=True)
    question = body.get("question", "").strip()
    conv_id  = body.get("conversation_id")
    if not question:
        return jsonify({"ok": False, "text": "Empty question"}), 400
    result = genie_ask(question, conv_id)
    return jsonify(result)

@app.route("/api/manuals/facets")
def api_manual_facets():
    """Aircraft types and systems available in the indexed manuals (cached)."""
    try:
        if not _facets_cache:
            rows = manuals_query("aircraft maintenance troubleshooting task", k=200, query_type="ANN")
            _facets_cache["aircraft_types"] = sorted({r["aircraft_type"] for r in rows if r.get("aircraft_type")})
            _facets_cache["systems"] = sorted({r["system"] for r in rows if r.get("system")})
        return jsonify({"ok": True, **_facets_cache})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/manuals/search", methods=["POST"])
def api_manual_search():
    body = request.get_json(force=True)
    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "Empty query"}), 400
    filters = {k: body[k] for k in ("aircraft_type", "system") if body.get(k)}
    try:
        return jsonify({"ok": True, "results": manuals_query(query, filters or None, k=int(body.get("k", 8)))})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# HTML  (single-page, vanilla JS, aviation cockpit theme)
# ---------------------------------------------------------------------------
PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parker Hannifin Component Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0b1120;--sidebar:#0f1a2e;--card:#152040;--accent:#00b4d8;
  --text:#e4eaf4;--muted:#7b8fa6;--border:#1c2e4a;--green:#06d6a0;
}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden}

/* sidebar */
.sidebar{width:230px;position:fixed;top:0;left:0;height:100vh;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;z-index:50}
.brand{text-align:center;padding:28px 16px 22px;border-bottom:1px solid var(--border)}
.brand .icon{font-size:32px}
.brand h1{font-size:17px;font-weight:700;margin:6px 0 2px}
.brand span{font-size:9.5px;letter-spacing:2.5px;color:var(--accent);font-weight:600}
nav{display:flex;flex-direction:column;gap:6px;padding:18px 14px}
nav button{width:100%;padding:13px 18px;border:none;border-radius:10px;cursor:pointer;font-size:13.5px;font-weight:600;display:flex;align-items:center;gap:10px;font-family:inherit;transition:all .15s;background:transparent;color:var(--muted)}
nav button.active{background:var(--accent);color:#fff}
nav button:hover:not(.active){background:rgba(0,180,216,.1)}
.spacer{flex:1}
.status{padding:16px 18px 20px;border-top:1px solid var(--border)}
.status h4{font-size:9px;letter-spacing:2px;color:var(--muted);margin-bottom:12px;font-weight:600}
.status-row{display:flex;align-items:center;gap:9px;margin-bottom:9px;font-size:12px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot.green{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.accent{background:var(--accent);box-shadow:0 0 6px var(--accent)}

/* main panel */
.main{margin-left:230px;height:100vh;display:flex;flex-direction:column;background:var(--bg)}
.header{display:flex;justify-content:space-between;align-items:center;padding:14px 28px;border-bottom:1px solid var(--border)}
.header h2{font-size:19px;font-weight:600}
.header p{font-size:12.5px;color:var(--muted);margin-top:3px}
.badge{font-size:11px;color:var(--muted);padding:5px 14px;border-radius:6px;border:1px solid var(--border);background:var(--card)}
.content{flex:1;overflow:hidden;position:relative}

/* views */
.view{position:absolute;inset:0;display:none}
.view.active{display:flex;flex-direction:column}
.view iframe{flex:1;border:none;width:100%;height:100%}

/* genie chat */
.genie-chat{flex:1;display:flex;flex-direction:column;overflow:hidden}
.chat-messages{flex:1;overflow-y:auto;padding:24px 28px}
.chat-messages::-webkit-scrollbar{width:6px}
.chat-messages::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.msg{max-width:85%;margin-bottom:16px;padding:14px 18px;border-radius:14px;font-size:14px;line-height:1.55}
.msg.user{margin-left:auto;background:var(--accent);color:#fff;border-bottom-right-radius:4px}
.msg.bot{background:var(--card);border:1px solid var(--border);border-bottom-left-radius:4px}
.msg pre{background:rgba(0,0,0,.3);padding:10px 12px;border-radius:8px;margin-top:8px;overflow-x:auto;font-size:12px;white-space:pre-wrap;font-family:'Fira Code','SF Mono',monospace}
.msg table{width:100%;border-collapse:collapse;margin-top:10px;font-size:12px;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.msg th{text-align:left;padding:8px 12px;background:rgba(0,180,216,.1);border-bottom:2px solid var(--border);color:var(--accent);font-weight:600;text-transform:uppercase;font-size:11px;letter-spacing:.5px}
.msg td{padding:7px 12px;border-bottom:1px solid rgba(255,255,255,.06)}
.msg tr:hover td{background:rgba(255,255,255,.03)}
.msg .chart-wrap{margin-top:12px;padding:16px;background:rgba(0,0,0,.2);border-radius:10px;border:1px solid var(--border);max-height:320px;position:relative}
.msg .chart-wrap canvas{max-height:280px}
.msg .viz-toggle{display:inline-flex;gap:4px;margin-top:8px}
.msg .viz-toggle button{padding:4px 12px;font-size:11px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--muted);cursor:pointer;font-family:inherit}
.msg .viz-toggle button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.msg .thinking{color:var(--muted);font-style:italic}
.chat-input{display:flex;gap:10px;padding:16px 28px;border-top:1px solid var(--border);background:var(--sidebar)}
.chat-input input{flex:1;padding:12px 16px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font-size:14px;font-family:inherit;outline:none}
.chat-input input:focus{border-color:var(--accent)}
.chat-input input::placeholder{color:var(--muted)}
.chat-input button{padding:12px 22px;border:none;border-radius:10px;background:var(--accent);color:#fff;font-weight:600;cursor:pointer;font-family:inherit;font-size:14px}
.chat-input button:disabled{opacity:.5;cursor:not-allowed}
.starters{display:flex;flex-wrap:wrap;gap:8px;padding:20px 28px}
.starters button{padding:10px 16px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font-size:13px;cursor:pointer;font-family:inherit;transition:all .15s}
.starters button:hover{border-color:var(--accent);background:rgba(0,180,216,.08)}

/* maintenance manuals */
.manuals{flex:1;display:flex;flex-direction:column;overflow:hidden}
.m-search{display:flex;gap:10px;padding:18px 28px;border-bottom:1px solid var(--border);background:var(--sidebar);flex-wrap:wrap}
.m-search input{flex:1;min-width:260px;padding:12px 16px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font-size:14px;font-family:inherit;outline:none}
.m-search input:focus{border-color:var(--accent)}
.m-search select{padding:12px;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font-family:inherit;font-size:13px;max-width:240px}
.m-search button{padding:12px 22px;border:none;border-radius:10px;background:var(--accent);color:#fff;font-weight:600;cursor:pointer;font-family:inherit;font-size:14px}
.m-search button:disabled{opacity:.5;cursor:not-allowed}
.m-examples{display:flex;flex-wrap:wrap;gap:8px;padding:14px 28px 0}
.m-examples button{padding:7px 13px;border:1px solid var(--border);border-radius:16px;background:transparent;color:var(--muted);font-size:12px;cursor:pointer;font-family:inherit}
.m-examples button:hover{border-color:var(--accent);color:var(--text)}
.m-results{flex:1;overflow-y:auto;padding:18px 28px 28px}
.m-note{color:var(--muted);font-size:13px;padding:6px 0 14px}
.m-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px 20px;margin-bottom:14px}
.m-card h3{font-size:15.5px;font-weight:600;margin-bottom:8px}
.m-meta{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chip{font-size:11px;padding:4px 10px;border-radius:12px;background:rgba(0,180,216,.12);color:var(--accent);font-weight:600}
.chip.pn{background:rgba(6,214,160,.14);color:var(--green);font-family:'Fira Code','SF Mono',monospace}
.chip.score{background:rgba(255,255,255,.06);color:var(--muted)}
.m-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 22px;font-size:13px;line-height:1.5}
.m-grid h4{font-size:10px;letter-spacing:1.5px;color:var(--muted);margin-bottom:4px;font-weight:600}
.m-grid .full{grid-column:1/-1}
.m-grid ol{padding-left:20px}
.m-grid li{margin-bottom:4px}
.m-actions{display:flex;gap:8px;margin-top:14px;align-items:center}
.m-actions button{padding:8px 14px;border:1px solid var(--accent);border-radius:8px;background:transparent;color:var(--accent);font-size:12.5px;font-weight:600;cursor:pointer;font-family:inherit}
.m-actions button:hover{background:rgba(0,180,216,.12)}
.m-actions span{font-size:11.5px;color:var(--muted)}
</style>
</head>
<body>
<!-- SIDEBAR -->
<aside class="sidebar">
  <div class="brand">
    <div class="icon">&#9992;</div>
    <h1>Parker Hannifin</h1>
    <span>COMPONENT INTELLIGENCE</span>
  </div>
  <nav>
    <button class="active" data-view="dashboard" onclick="switchView('dashboard',this)">&#128202; Dashboard</button>
    <button data-view="genie" onclick="switchView('genie',this)">&#129302; Genie AI</button>
    <button data-view="manuals" onclick="switchView('manuals',this)">&#128216; Maintenance Manuals</button>
  </nav>
  <div class="spacer"></div>
  <div class="status">
    <h4>SYSTEM STATUS</h4>
    <div class="status-row"><span class="dot green"></span>Lakebase Online</div>
    <div class="status-row"><span class="dot green"></span>11 UC Tables</div>
    <div class="status-row"><span class="dot green"></span>ML Failure Model Active</div>
    <div class="status-row"><span class="dot accent"></span>1,640 Components Scored</div>
  </div>
</aside>

<!-- MAIN -->
<main class="main">
  <div class="header" id="hdr">
    <div>
      <h2 id="hdr-title">Component Maintenance Dashboard</h2>
      <p id="hdr-sub">Parker Hannifin aerospace component analytics powered by Databricks</p>
    </div>
    <span class="badge">Powered by Databricks</span>
  </div>

  <div class="content">
    <!-- Dashboard view -->
    <div class="view active" id="v-dashboard">
      <iframe src="{{ dashboard_url }}" allow="clipboard-write"></iframe>
    </div>

    <!-- Genie chat view -->
    <div class="view" id="v-genie">
      <div class="genie-chat">
        <div class="chat-messages" id="chat-box">
          <div class="msg bot">
            <strong>Genie AI</strong> &mdash; Parker Component Maintenance Intelligence<br><br>
            Ask me anything about Parker components, maintenance compliance, failure predictions, warranty exposure, or airline customer operations.
          </div>
          <div class="starters" id="starters">
            <button onclick="askStarter(this)">Which components need EMERGENCY_GROUND?</button>
            <button onclick="askStarter(this)">Top maintenance anomaly types by frequency</button>
            <button onclick="askStarter(this)">Airlines with highest warranty exposure</button>
            <button onclick="askStarter(this)">Component health summary by type</button>
            <button onclick="askStarter(this)">FLIGHT_CRITICAL components with active anomalies</button>
          </div>
        </div>
        <div class="chat-input">
          <input id="q" placeholder="Ask about Parker component maintenance data..." onkeydown="if(event.key==='Enter')sendMsg()">
          <button id="send-btn" onclick="sendMsg()">Send</button>
        </div>
      </div>
    </div>

    <!-- Maintenance manuals view -->
    <div class="view" id="v-manuals">
      <div class="manuals">
        <div class="m-search">
          <input id="mq" placeholder="Describe the fault or enter a part number, e.g. 'brake very hot after landing'" onkeydown="if(event.key==='Enter')searchManuals()">
          <select id="f-ac"><option value="">All aircraft types</option></select>
          <select id="f-sys"><option value="">All systems</option></select>
          <button id="m-btn" onclick="searchManuals()">Search</button>
        </div>
        <div class="m-examples">
          <button onclick="exampleSearch(this)">Brake overheating after landing, fuse plug melted</button>
          <button onclick="exampleSearch(this)">Engine vibration high in climb</button>
          <button onclick="exampleSearch(this)">Oil pressure low and chip detector warning</button>
          <button onclick="exampleSearch(this)">Bleed leak warning on the wing</button>
          <button onclick="exampleSearch(this)">B738-3242-117</button>
        </div>
        <div class="m-results" id="m-results">
          <div class="m-note">Search the aircraft maintenance manual library by symptom, part name or part number. Results show the broken part, its part number, and the step-by-step corrective action from the manual. (Demo library: synthetic manuals, not OEM data.)</div>
        </div>
      </div>
    </div>
  </div>
</main>

<script>
let convId = null;

function switchView(name, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('v-'+name).classList.add('active');
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (name==='dashboard') {
    document.getElementById('hdr-title').textContent='Component Maintenance Dashboard';
    document.getElementById('hdr-sub').textContent='Parker Hannifin aerospace component analytics powered by Databricks';
  } else if (name==='manuals') {
    document.getElementById('hdr-title').textContent='Maintenance Manuals';
    document.getElementById('hdr-sub').textContent='Find the broken part and the manual fix, powered by Databricks Vector Search';
    loadFacets();
    document.getElementById('mq').focus();
  } else {
    document.getElementById('hdr-title').textContent='Genie AI Assistant';
    document.getElementById('hdr-sub').textContent='Ask natural-language questions about Parker component maintenance data';
  }
}

// ---------------- Maintenance manuals ----------------
let facetsLoaded = false;
async function loadFacets() {
  if (facetsLoaded) return;
  try {
    const d = await (await fetch('/api/manuals/facets')).json();
    if (!d.ok) return;
    const fill = (id, vals) => { const s = document.getElementById(id);
      vals.forEach(v => { const o = document.createElement('option'); o.value = v; o.textContent = v; s.appendChild(o); }); };
    fill('f-ac', d.aircraft_types || []); fill('f-sys', d.systems || []);
    facetsLoaded = true;
  } catch (e) { /* filters stay at 'All' */ }
}

function exampleSearch(btn) { document.getElementById('mq').value = btn.textContent; searchManuals(); }

async function searchManuals() {
  const query = document.getElementById('mq').value.trim();
  if (!query) return;
  const btn = document.getElementById('m-btn'); btn.disabled = true;
  const box = document.getElementById('m-results');
  box.innerHTML = '<div class="m-note">Searching manuals...</div>';
  try {
    const resp = await fetch('/api/manuals/search', { method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ query, aircraft_type: document.getElementById('f-ac').value, system: document.getElementById('f-sys').value }) });
    const d = await resp.json();
    if (!d.ok) { box.innerHTML = `<div class="m-note">Search failed: ${esc(d.error || 'unknown error')}</div>`; return; }
    if (!d.results.length) { box.innerHTML = '<div class="m-note">No matching manual tasks. Try different words or clear the filters.</div>'; return; }
    box.innerHTML = `<div class="m-note">${d.results.length} matching manual tasks for "${esc(query)}"</div>` + d.results.map(renderManual).join('');
  } catch (e) {
    box.innerHTML = `<div class="m-note">Search failed: ${esc(String(e))}</div>`;
  } finally { btn.disabled = false; }
}

function renderManual(r) {
  const steps = (r.corrective_steps || '').split('\n').filter(Boolean).map(s => `<li>${esc(s)}</li>`).join('');
  const score = r.score != null ? `<span class="chip score">relevance ${Number(r.score).toFixed(3)}</span>` : '';
  return `<div class="m-card">
    <h3>${esc(r.task_title || '')}</h3>
    <div class="m-meta">
      <span class="chip">${esc(r.aircraft_type || '')}</span><span class="chip">${esc(r.engine || '')}</span>
      <span class="chip">ATA ${esc(r.ata_chapter || '')}</span><span class="chip">${esc(r.system || '')}</span>
      <span class="chip pn">${esc(r.part_number || '')}</span>${score}
    </div>
    <div class="m-grid">
      <div><h4>PART</h4>${esc(r.part_name || '')}</div>
      <div><h4>RELATED PARTS</h4>${esc(r.related_parts || '')}</div>
      <div class="full"><h4>SYMPTOMS</h4>${esc(r.symptoms || '')}</div>
      <div class="full"><h4>PROBABLE CAUSES</h4>${esc(r.probable_causes || '')}</div>
      <div class="full"><h4>CORRECTIVE ACTION</h4><ol>${steps}</ol></div>
      <div><h4>LIMITS</h4>${esc(r.limits || '')}</div>
      <div><h4>TORQUE VALUES</h4>${esc(r.torque_values || '')}</div>
    </div>
    <div class="m-actions">
      <button onclick="askGenieAbout('${esc(r.fault_code || '')}','${esc(r.aircraft_type || '')}')">Ask Genie which aircraft have this fault</button>
      <span>Source: ${esc(r.manual_name || '')}</span>
    </div>
  </div>`;
}

function askGenieAbout(code, ac) {
  switchView('genie', document.querySelector('nav button[data-view="genie"]'));
  document.getElementById('starters').style.display = 'none';
  document.getElementById('q').value = `Which ${ac} aircraft have had ${code} anomalies, and what is their current maintenance risk category?`;
  sendMsg();
}

function askStarter(btn) {
  document.getElementById('q').value = btn.textContent;
  document.getElementById('starters').style.display='none';
  sendMsg();
}

async function sendMsg() {
  const inp = document.getElementById('q');
  const question = inp.value.trim();
  if (!question) return;
  inp.value = '';
  const btn = document.getElementById('send-btn');
  btn.disabled = true;

  const box = document.getElementById('chat-box');
  // user bubble
  box.innerHTML += `<div class="msg user">${esc(question)}</div>`;
  // thinking indicator
  const thinkId = 'think-'+Date.now();
  box.innerHTML += `<div class="msg bot" id="${thinkId}"><span class="thinking">Thinking...</span></div>`;
  box.scrollTop = box.scrollHeight;

  try {
    const resp = await fetch('/api/genie', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question, conversation_id: convId})
    });
    const data = await resp.json();
    convId = data.conversation_id || convId;
    let html = '';
    if (data.text) html += `<div>${fmtMd(data.text)}</div>`;
    if (data.sql)  html += `<pre>${esc(data.sql)}</pre>`;
    if (data.table && data.table.columns && data.table.rows && data.table.rows.length>0) {
      const cid = 'ch'+Date.now();
      const t = data.table;
      // detect numeric columns
      const numI=[], lblI=[];
      t.columns.forEach((_,i)=>{
        const tp=(t.types&&t.types[i]||'').toUpperCase();
        const isNum=['INT','LONG','FLOAT','DOUBLE','DECIMAL','SHORT','BYTE','BIGINT','NUMERIC'].some(n=>tp.includes(n))
          || t.rows.every(r=>r[i]===null||r[i]===''||!isNaN(Number(r[i])))&&t.rows.some(r=>r[i]!==null&&r[i]!=='');
        if(isNum) numI.push(i); else lblI.push(i);
      });
      const canChart=lblI.length>=1&&numI.length>=1&&t.rows.length>1&&t.rows.length<=80;
      // table
      html+='<table><tr>'+t.columns.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr>';
      t.rows.forEach(r=>{
        html+='<tr>'+r.map((v,i)=>{
          let s=v===null?'':String(v);
          if(numI.includes(i)&&s){const n=parseFloat(s);if(!isNaN(n))s=n%1?n.toFixed(2):n.toLocaleString();}
          return '<td>'+esc(s)+'</td>';
        }).join('')+'</tr>';
      });
      html+='</table>';
      // chart
      if(canChart){
        html+=`<div class="viz-toggle" id="vt-${cid}">`;
        html+=`<button class="active" onclick="showChart('${cid}','bar',this)">Bar</button>`;
        html+=`<button onclick="showChart('${cid}','doughnut',this)">Donut</button>`;
        html+=`<button onclick="showChart('${cid}','line',this)">Line</button>`;
        html+=`</div>`;
        html+=`<div class="chart-wrap"><canvas id="${cid}"></canvas></div>`;
        setTimeout(()=>{window._cd=window._cd||{};window._cd[cid]={t,lblI,numI};buildChart(cid,'bar');},80);
      }
    }
    if (!html) html = '<span class="thinking">No response</span>';
    document.getElementById(thinkId).innerHTML = html;
  } catch(e) {
    document.getElementById(thinkId).innerHTML = `<span class="thinking">Error: ${esc(e.message)}</span>`;
  }
  btn.disabled = false;
  box.scrollTop = box.scrollHeight;
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function fmtMd(s){
  // Bold **text**
  s=s.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  // Inline code `text`
  s=s.replace(/`([^`]+)`/g,'<code style="background:rgba(0,180,216,.15);padding:1px 5px;border-radius:4px;font-size:12px">$1</code>');
  // Line breaks
  s=s.replace(/\n/g,'<br>');
  return s;
}

const PALETTE=['#00b4d8','#06d6a0','#ffd166','#ef476f','#8338ec','#ff6b6b','#48bfe3','#72efdd','#f77f00','#d62828','#4cc9f0','#7209b7'];
window._charts={};

function buildChart(cid,type){
  const d=window._cd[cid]; if(!d) return;
  const {t,lblI,numI}=d;
  const labels=t.rows.map(r=>r[lblI[0]]===null?'':String(r[lblI[0]]));
  const datasets=numI.map((ni,di)=>({
    label:t.columns[ni],
    data:t.rows.map(r=>{const v=r[ni];return v===null?0:parseFloat(v)||0;}),
    backgroundColor:type==='doughnut'?PALETTE.slice(0,t.rows.length):PALETTE[di%PALETTE.length],
    borderColor:type==='line'?PALETTE[di%PALETTE.length]:'transparent',
    borderWidth:type==='line'?2:0,
    borderRadius:type==='bar'?4:0,
    tension:.3,
    fill:type==='line'?false:undefined,
  }));
  if(window._charts[cid]){window._charts[cid].destroy();}
  const ctx=document.getElementById(cid);
  if(!ctx)return;
  window._charts[cid]=new Chart(ctx,{
    type:type,
    data:{labels,datasets},
    options:{
      responsive:true,
      maintainAspectRatio:false,
      plugins:{
        legend:{display:numI.length>1||type==='doughnut',labels:{color:'#7b8fa6',font:{size:11}}},
        tooltip:{backgroundColor:'#152040',titleColor:'#e4eaf4',bodyColor:'#e4eaf4',borderColor:'#1c2e4a',borderWidth:1},
      },
      scales:type==='doughnut'?{}:{
        x:{ticks:{color:'#7b8fa6',font:{size:10},maxRotation:45},grid:{color:'rgba(255,255,255,.04)'}},
        y:{ticks:{color:'#7b8fa6',font:{size:10}},grid:{color:'rgba(255,255,255,.06)'},beginAtZero:true}
      }
    }
  });
}

function showChart(cid,type,btn){
  btn.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  buildChart(cid,type);
}
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
