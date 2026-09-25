"""Aircraft Predictive Maintenance Intelligence App.

Flask app that embeds the AI/BI dashboard via iframe and provides
a custom Genie chat interface powered by the Databricks SDK.
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


# ---------------------------------------------------------------------------
# HTML  (single-page, vanilla JS, aviation cockpit theme)
# ---------------------------------------------------------------------------
PAGE_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aircraft PdM Intelligence</title>
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
</style>
</head>
<body>
<!-- SIDEBAR -->
<aside class="sidebar">
  <div class="brand">
    <div class="icon">&#9992;</div>
    <h1>Aircraft PdM</h1>
    <span>INTELLIGENCE PLATFORM</span>
  </div>
  <nav>
    <button class="active" onclick="switchView('dashboard',this)">&#128202; Dashboard</button>
    <button onclick="switchView('genie',this)">&#129302; Genie AI</button>
  </nav>
  <div class="spacer"></div>
  <div class="status">
    <h4>SYSTEM STATUS</h4>
    <div class="status-row"><span class="dot green"></span>Lakebase Online</div>
    <div class="status-row"><span class="dot green"></span>5 Synced Tables</div>
    <div class="status-row"><span class="dot green"></span>ML Models Active</div>
    <div class="status-row"><span class="dot accent"></span>310 Aircraft Scored</div>
  </div>
</aside>

<!-- MAIN -->
<main class="main">
  <div class="header" id="hdr">
    <div>
      <h2 id="hdr-title">Fleet Operations Dashboard</h2>
      <p id="hdr-sub">Real-time fleet analytics powered by Lakebase</p>
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
            <strong>Genie AI</strong> &mdash; Aircraft Maintenance Intelligence<br><br>
            Ask me anything about your fleet, anomalies, maintenance predictions, or airline operations.
          </div>
          <div class="starters" id="starters">
            <button onclick="askStarter(this)">Which aircraft are CRITICAL risk?</button>
            <button onclick="askStarter(this)">Top anomaly types by frequency</button>
            <button onclick="askStarter(this)">Airlines with highest anomaly rate</button>
            <button onclick="askStarter(this)">Fleet health summary</button>
            <button onclick="askStarter(this)">Overdue maintenance aircraft</button>
          </div>
        </div>
        <div class="chat-input">
          <input id="q" placeholder="Ask about aircraft maintenance data..." onkeydown="if(event.key==='Enter')sendMsg()">
          <button id="send-btn" onclick="sendMsg()">Send</button>
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
    document.getElementById('hdr-title').textContent='Fleet Operations Dashboard';
    document.getElementById('hdr-sub').textContent='Real-time fleet analytics powered by Lakebase';
  } else {
    document.getElementById('hdr-title').textContent='Genie AI Assistant';
    document.getElementById('hdr-sub').textContent='Ask natural-language questions about aircraft maintenance data';
  }
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
