import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from backend.telemetry.state import global_state

BROADCAST_INTERVAL_S = 0.1

app = FastAPI(title="Solaris Ground Station")


@app.get("/")
def root():
    return {"status": "ok", "ws": "/ws", "state": "/state"}


@app.get("/state")
def get_state():
    return global_state.current_state()


_LIVE_PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Solaris · Live</title>
<style>
  body { background:#101b24; color:#e8eef1; font-family:ui-monospace,Consolas,monospace; margin:0; padding:1.5rem; }
  h1 { font-size:1rem; color:#79c6d4; letter-spacing:.1em; text-transform:uppercase; margin:0 0 1rem; }
  #status { font-size:.85rem; margin-bottom:1rem; }
  pre { background:#17252f; border:1px solid #24333d; border-radius:8px; padding:1rem; overflow:auto; font-size:.85rem; }
</style>
</head>
<body>
  <h1>Solaris · Telemetría en vivo</h1>
  <div id="status">conectando…</div>
  <pre id="out">—</pre>
<script>
  const status = document.getElementById("status");
  const out = document.getElementById("out");
  const ws = new WebSocket("ws://" + location.host + "/ws");
  ws.onopen  = () => { status.textContent = "● conectado a /ws"; status.style.color = "#57c793"; };
  ws.onclose = () => { status.textContent = "○ desconectado"; status.style.color = "#d9584a"; };
  ws.onmessage = (e) => { out.textContent = JSON.stringify(JSON.parse(e.data), null, 2); };
</script>
</body>
</html>"""


@app.get("/live", response_class=HTMLResponse)
def live():
    return _LIVE_PAGE


@app.websocket("/ws")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            state = global_state.current_state()
            await websocket.send_text(json.dumps(state))
            await asyncio.sleep(BROADCAST_INTERVAL_S)
    except WebSocketDisconnect:
        pass