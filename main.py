"""
OmniWatch Civil Defense Network
A lightweight neighborhood visibility and trust network application.

Improvements over the original:
- Protected admin routes
- Consistent HTML rendering helper
- Input validation and upload limits
- Structured logging
- All routes defined before application entry point
- Cleaner separation of concerns within a single file
"""

import os
import hmac
import hashlib
import html
import logging
import aiosqlite
import shutil
import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import (
    FastAPI, Form, Response, Depends, HTTPException,
    Cookie, UploadFile, File, Request
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
COOKIE_SIGNING_KEY = os.getenv("COOKIE_SECRET_KEY", "grid-security-core-token-991").encode()
ADMIN_KEY = os.getenv("ADMIN_KEY", "change-me-admin-key")
DB_FILE = os.getenv("DB_FILE", "omni_matrix_final.db")
UPLOAD_DIR = Path("static/profile_pics")
BACKUP_DIR = Path("backups")
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("omniwatch")

CITY_AUTOFILL_MAP: Dict[str, Dict[str, str]] = {
    "osogbo": {"country": "Nigeria", "state": "Osun", "lga": "Osogbo", "area": "Ataoja Sector"},
    "ile-ife": {"country": "Nigeria", "state": "Osun", "lga": "Ile-Ife", "area": "Ife Central Town"},
    "ibadan": {"country": "Nigeria", "state": "Oyo", "lga": "Ibadan", "area": "Ido Sector Grid"},
    "ogbomoso": {"country": "Nigeria", "state": "Oyo", "lga": "Ogbomoso", "area": "Ogbomoso South Central"},
}

# ---------------------------------------------------------------------------
# Shared HTML / CSS
# ---------------------------------------------------------------------------
BASE_CSS = """
:root {
  --bg-slate: #0b1020;
  --panel-glass: rgba(18, 26, 44, 0.72);
  --border-glass: rgba(255, 255, 255, 0.07);
  --accent-emerald: #34d399;
  --accent-blue: #60a5fa;
  --accent-lavender: #c4b5fd;
  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
}
body {
  font-family: system-ui, -apple-system, sans-serif;
  background:
    radial-gradient(ellipse 80% 50% at 15% 10%, rgba(139, 92, 246, 0.14) 0%, transparent 55%),
    radial-gradient(ellipse 60% 40% at 85% 75%, rgba(56, 189, 248, 0.12) 0%, transparent 50%),
    radial-gradient(ellipse 50% 30% at 50% 100%, rgba(244, 114, 182, 0.08) 0%, transparent 45%),
    linear-gradient(180deg, #0f172a 0%, #0b1020 100%);
  color: var(--text-main);
  margin: 0;
  padding: 20px;
  padding-bottom: 120px;
  min-height: 100vh;
  background-attachment: fixed;
}
.glass-panel {
  background: var(--panel-glass);
  border: 1px solid var(--border-glass);
  border-radius: 24px;
  padding: 30px;
  box-shadow: 0 20px 50px -12px rgba(0,0,0,0.45), 0 0 30px rgba(96, 165, 250, 0.04);
  backdrop-filter: blur(10px);
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}
.badge-green { background: rgba(16, 185, 129, 0.15); color: #34d399; }
.badge-red { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.badge-gray { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--panel-glass);
  border: 1px solid var(--border-glass);
  border-radius: 16px;
  padding: 18px 20px;
  text-align: center;
}
.stat-card .value { font-size: 28px; font-weight: 800; color: #fff; }
.stat-card .label { font-size: 12px; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
.dash-header { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.table-wrap { overflow-x: auto; }
table.admin-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
table.admin-table th {
  background: rgba(255,255,255,0.04);
  font-weight: 600;
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-glass);
}
table.admin-table td { padding: 12px; border-bottom: 1px solid var(--border-glass); vertical-align: middle; }
table.admin-table tr:hover td { background: rgba(255,255,255,0.02); }
.action-group { display: flex; gap: 6px; flex-wrap: wrap; }
.btn-sm { padding: 6px 12px; font-size: 12px; border-radius: 8px; }
.btn-success { background: #10b981; color: white; }
.btn-danger { background: #ef4444; color: white; }
.empty-state { text-align: center; color: var(--text-muted); padding: 24px; font-style: italic; }
.search-bar { margin-bottom: 12px; max-width: 280px; }
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 14px 20px;
  border-radius: 12px;
  font-weight: 700;
  text-decoration: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
}
.btn-blue { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; }
input[type="text"], select, textarea {
  width: 100%;
  padding: 12px;
  background: #090d16;
  border: 1px solid var(--border-glass);
  color: white;
  border-radius: 10px;
  box-sizing: border-box;
  margin-top: 4px;
  margin-bottom: 10px;
}
label { color: var(--text-muted); font-size: 13px; font-weight: 600; }
.comment-box {
  background: rgba(255,255,255,0.03);
  padding: 8px;
  border-radius: 6px;
  margin-top: 6px;
  font-size: 13px;
  text-align: left;
  border-left: 2px solid var(--accent-blue);
}
.instruction-text {
  background: rgba(59,130,246,0.06);
  border-left: 3px solid var(--accent-blue);
  padding: 10px;
  border-radius: 6px;
  font-size: 13px;
  color: #cbd5e1;
  text-align: left;
  margin-bottom: 15px;
}
.retro-envelope {
  width: 22px;
  height: 14px;
  background: #fffdf6;
  border: 1px solid #7f1d1d;
  display: inline-block;
  box-shadow: 1px 2px 4px rgba(0,0,0,0.4);
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px; border-bottom: 1px solid var(--border-glass); text-align: left; color: #fff; }
"""

SOCIAL_FOOTER = """
<footer style="margin-top:40px; text-align:center; padding:20px; border-top:1px solid var(--border-glass);">
  <div style="display:flex; justify-content:center; gap:15px; font-size:13px;">
    <a href="https://x.com" target="_blank" style="color:#3b82f6; text-decoration:none; font-weight:700;">X / Twitter</a>
    <a href="https://facebook.com" target="_blank" style="color:#3b82f6; text-decoration:none; font-weight:700;">Facebook</a>
    <a href="https://whatsapp.com" target="_blank" style="color:#10b981; text-decoration:none; font-weight:700;">WhatsApp</a>
  </div>
</footer>
"""

def render_page(title: str, body: str, extra_head: str = "") -> str:
    """Wrap content in a consistent HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} · OmniWatch</title>
  <style>{BASE_CSS}</style>
  {extra_head}
</head>
<body>
{body}
{SOCIAL_FOOTER}
</body>
</html>"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clean_phone(phone: str) -> str:
    """Normalize Nigerian phone numbers to 10-digit form."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("234") and len(digits) > 10:
        digits = digits[3:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits

def sanitize(text: str, max_len: int = 500) -> str:
    """Escape HTML and enforce length."""
    return html.escape(text.strip()[:max_len])

def sign_cookie_value(value: str) -> str:
    sig = hmac.new(COOKIE_SIGNING_KEY, value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"

def verify_cookie_value(signed_value: Optional[str]) -> Optional[str]:
    if not signed_value or "." not in signed_value:
        return None
    value, signature = signed_value.rsplit(".", 1)
    expected = hmac.new(COOKIE_SIGNING_KEY, value.encode(), hashlib.sha256).hexdigest()
    return value if hmac.compare_digest(signature, expected) else None

def generate_music_embed(provider: str, url: str) -> str:
    """Return a safe embed or external link for supported music platforms."""
    if not url:
        return ""
    url = url.strip()
    try:
        low = url.lower()
        if "spotify.com" in low:
            embed = url.replace("/track/", "/embed/track/").replace("/playlist/", "/embed/playlist/").replace("/album/", "/embed/album/")
            return f'<iframe src="{html.escape(embed)}" width="100%" height="152" frameborder="0" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" style="border-radius:12px; margin-top:10px;" loading="lazy"></iframe>'
        if "music.apple.com" in low or "apple.com" in low:
            embed = url.replace("://music.apple.com", "://embed.music.apple.com").replace("://apple.com", "://embed.apple.com")
            return f'<iframe src="{html.escape(embed)}" width="100%" height="175" frameborder="0" allow="autoplay *; encrypted-media *; fullscreen *" style="border-radius:12px; margin-top:10px;"></iframe>'
        if "audiomack.com" in low:
            embed = url if "embed" in low else url.replace("audiomack.com", "audiomack.com/embed")
            return f'<iframe src="{html.escape(embed)}" width="100%" height="250" frameborder="0" allowtransparency="true" allow="autoplay; encrypted-media" style="border-radius:12px; margin-top:10px;"></iframe>'
    except Exception as exc:
        logger.warning("Music embed failed: %s", exc)
    return f'<p style="font-size:11px; color:var(--text-muted);">🎵 <a href="{html.escape(url)}" target="_blank" style="color:var(--accent-blue);">External Music Stream</a></p>'

async def get_current_citizen(citizen_session: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    verified = verify_cookie_value(citizen_session)
    if not verified:
        raise HTTPException(status_code=401, detail="Unauthorized")
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (verified,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Terminal unrecognized")
            return dict(row)

async def require_admin(admin_key: Optional[str] = Cookie(None), key: Optional[str] = None) -> bool:
    """Simple admin gate. Accepts cookie or query parameter."""
    provided = admin_key or key
    if provided != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")
    return True

# ---------------------------------------------------------------------------
# Lifespan / DB init
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if Path(DB_FILE).exists():
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(DB_FILE, BACKUP_DIR / f"backup_{ts}.db")
        logger.info("Database backup created: backup_%s.db", ts)

    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS citizens (
                phone TEXT PRIMARY KEY,
                name TEXT,
                country TEXT,
                state TEXT,
                city TEXT,
                lga TEXT,
                area TEXT,
                token TEXT,
                status TEXT,
                xp INTEGER DEFAULT 100,
                profile_pic TEXT DEFAULT '',
                music_provider TEXT DEFAULT '',
                music_url TEXT DEFAULT ''
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS viral_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                author TEXT,
                phone TEXT,
                context TEXT,
                status TEXT,
                reshares INTEGER DEFAULT 0,
                visibility TEXT DEFAULT 'Public'
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS viral_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER,
                author TEXT,
                phone TEXT,
                text TEXT,
                status TEXT DEFAULT 'Approved',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trust_network (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                receiver TEXT,
                status TEXT,
                UNIQUE(sender, receiver)
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS direct_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                receiver TEXT,
                message TEXT,
                status TEXT DEFAULT 'Active',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Safe migrations
        for stmt in (
            "ALTER TABLE viral_posts ADD COLUMN visibility TEXT DEFAULT 'Public';",
            "ALTER TABLE direct_messages ADD COLUMN status TEXT DEFAULT 'Active';",
        ):
            try:
                await conn.execute(stmt)
            except Exception:
                pass

        await conn.execute("""
            INSERT OR IGNORE INTO citizens
            (phone, name, country, state, city, lga, area, token, status, xp)
            VALUES ('8031112225', 'Officer Adewale', 'Nigeria', 'Osun', 'Osogbo', 'Osogbo', 'Ataoja Sector', 'm1', 'Approved', 450)
        """)
        await conn.commit()
    logger.info("Database ready")
    yield
    logger.info("Shutting down")

app = FastAPI(
    title="OmniWatch Civil Defense Network",
    version="1.3.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------
@app.get("/favicon.ico", include_in_schema=False)
@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def icon_fallback():
    return Response(status_code=204)

@app.get("/health")
def health():
    return {"status": "ok", "service": "omniwatch"}

@app.get("/", response_class=HTMLResponse)
def community_homepage():
    logo = '''<svg width="90" height="90" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        <circle cx="12" cy="11" r="3" stroke="#10b981"/>
        <circle cx="12" cy="11" r="1" fill="#10b981"/>
    </svg>'''
    body = f"""
    <div class="glass-panel" style="max-width:520px; margin:40px auto; text-align:center;">
        {logo}
        <h1 style="font-size:34px; font-weight:900; color:#fff; margin:10px 0;">omniwatch.com.ng</h1>
        <span class="badge badge-blue">Decentralized Civil Defense Grid</span>
        <p style="color:var(--text-muted); font-size:14px; margin:15px 0;">
            Multiplying neighborhood visibility by linking verified citizens and law enforcement into a single network.
        </p>
        <div style="display:grid; gap:10px;">
            <a href="/register" class="btn btn-blue">Register</a>
            <a href="/portal/login" class="btn" style="background:rgba(255,255,255,0.04); color:#fff;">Sign In</a>
            <a href="/games" class="btn" style="background:rgba(196,181,253,0.15); color:#c4b5fd;">Fun Zone</a>
            <a href="/dashboard" class="btn" style="background:linear-gradient(135deg,#10b981,#059669); color:white;">Control Matrix</a>
        </div>
    </div>
    """
    return HTMLResponse(render_page("Home", body))

@app.get("/games", response_class=HTMLResponse)
def games_page():
    """Fun Zone with several addictive mini-games and local high scores."""
    body = """
    <div class="glass-panel" style="max-width:640px; margin:30px auto;">
        <h2 style="margin-top:0; text-align:center;">Fun Zone</h2>
        <p style="text-align:center; color:var(--text-muted); font-size:14px; margin-bottom:20px;">Pick a game. Beat your high score.</p>
        <div style="display:flex; gap:8px; justify-content:center; flex-wrap:wrap; margin-bottom:20px;">
            <button onclick="show('xoxo')" class="btn" style="background:rgba(96,165,250,0.15); color:#60a5fa; padding:10px 16px;">XOXO</button>
            <button onclick="show('memory')" class="btn" style="background:rgba(196,181,253,0.15); color:#c4b5fd; padding:10px 16px;">Memory</button>
            <button onclick="show('tap')" class="btn" style="background:rgba(52,211,153,0.15); color:#34d399; padding:10px 16px;">Speed Tap</button>
            <button onclick="show('snake')" class="btn" style="background:rgba(244,114,182,0.15); color:#f472b6; padding:10px 16px;">Snake</button>
        </div>
        <div id="gameArea" style="min-height:340px;"></div>
        <br>
        <center><a href="/" class="btn" style="background:rgba(255,255,255,0.06); color:#cbd5e1;">Back Home</a></center>
    </div>
    <script>
    const hs = (k) => +localStorage.getItem(k) || 0;
    const setHs = (k, v) => { if (v > hs(k)) localStorage.setItem(k, v); };
    function show(name) {
        const area = document.getElementById('gameArea');
        if (name === 'xoxo') area.innerHTML = xoxoHTML();
        if (name === 'memory') area.innerHTML = memoryHTML();
        if (name === 'tap') area.innerHTML = tapHTML();
        if (name === 'snake') area.innerHTML = snakeHTML();
        if (name === 'xoxo') initXoxo();
        if (name === 'memory') initMemory();
        if (name === 'tap') initTap();
        if (name === 'snake') initSnake();
    }
    function xoxoHTML(){ return `<h3 style="text-align:center;">XOXO</h3><div id="board" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:280px;margin:0 auto 12px;"></div><p id="status" style="text-align:center;font-weight:600;color:#c4b5fd;"></p><center><button onclick="initXoxo()" class="btn btn-blue" style="padding:8px 16px;">New Game</button></center>`; }
    function memoryHTML(){ return `<h3 style="text-align:center;">Memory Match</h3><p style="text-align:center;font-size:13px;color:var(--text-muted);">High: <span id="memHs">${hs('mem')}</span></p><div id="memBoard" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;max-width:320px;margin:0 auto;"></div><p id="memStatus" style="text-align:center;margin-top:10px;"></p>`; }
    function tapHTML(){ return `<h3 style="text-align:center;">Speed Tap</h3><p style="text-align:center;font-size:13px;color:var(--text-muted);">Best: <span id="tapHs">${hs('tap')}</span></p><div id="tapArea" style="height:260px;background:rgba(255,255,255,0.03);border-radius:16px;position:relative;margin:10px 0;"></div><p id="tapScore" style="text-align:center;font-weight:700;font-size:20px;">0</p><center><button onclick="startTap()" class="btn btn-blue" style="padding:8px 16px;">Start (15s)</button></center>`; }
    function snakeHTML(){ return `<h3 style="text-align:center;">Snake</h3><p style="text-align:center;font-size:13px;color:var(--text-muted);">Best: <span id="snakeHs">${hs('snake')}</span></p><canvas id="snakeCanvas" width="300" height="300" style="display:block;margin:10px auto;background:#0f172a;border-radius:12px;"></canvas><p style="text-align:center;font-size:12px;color:var(--text-muted);">Arrow keys or swipe</p>`; }

    // XOXO
    let cells, turn, done;
    function initXoxo(){
        cells = Array(9).fill(null); turn='X'; done=false;
        const board = document.getElementById('board');
        board.innerHTML='';
        cells.forEach((_,i)=>{
            const d=document.createElement('div');
            d.style.cssText='height:80px;background:rgba(255,255,255,0.04);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:700;cursor:pointer;';
            d.onclick=()=>playX(i); board.appendChild(d);
        });
        document.getElementById('status').textContent="X's turn";
    }
    function playX(i){
        if(done||cells[i])return;
        cells[i]=turn; turn=turn==='X'?'O':'X';
        done=!!winX()||cells.every(c=>c);
        document.querySelectorAll('#board div').forEach((d,idx)=>{d.textContent=cells[idx]||''; d.style.color=cells[idx]==='X'?'#60a5fa':'#f472b6';});
        document.getElementById('status').textContent=done?(winX()?winX()+' wins':'Draw'):turn+"'s turn";
    }
    function winX(){const L=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]; for(const [a,b,c] of L) if(cells[a]&&cells[a]===cells[b]&&cells[a]===cells[c])return cells[a]; return null;}

    // Memory
    function initMemory(){
        const icons=['🌙','⭐','🔥','💧','🍀','🎵','⚡','💎'];
        let deck=[...icons,...icons].sort(()=>Math.random()-0.5);
        let flipped=[], matched=0, moves=0;
        const board=document.getElementById('memBoard');
        board.innerHTML='';
        deck.forEach((ic,i)=>{
            const d=document.createElement('div');
            d.style.cssText='height:70px;background:rgba(255,255,255,0.05);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:28px;cursor:pointer;';
            d.dataset.i=i; d.dataset.ic=ic; d.textContent='?';
            d.onclick=()=>flip(d); board.appendChild(d);
        });
        function flip(el){
            if(flipped.length>=2||el.textContent!=='?')return;
            el.textContent=el.dataset.ic; flipped.push(el);
            if(flipped.length===2){
                moves++;
                setTimeout(()=>{
                    if(flipped[0].dataset.ic===flipped[1].dataset.ic){ matched++; flipped.forEach(e=>e.style.opacity=0.4); }
                    else flipped.forEach(e=>e.textContent='?');
                    flipped=[];
                    if(matched===8){ setHs('mem', Math.max(0, 20-moves)); document.getElementById('memHs').textContent=hs('mem'); document.getElementById('memStatus').textContent='Cleared in '+moves+' moves!'; }
                },600);
            }
        }
    }

    // Speed Tap
    let tapScore=0, tapTimer;
    function initTap(){ document.getElementById('tapScore').textContent='0'; }
    function startTap(){
        tapScore=0; document.getElementById('tapScore').textContent='0';
        const area=document.getElementById('tapArea');
        area.innerHTML='';
        let time=15;
        const tick=setInterval(()=>{
            time--; if(time<=0){ clearInterval(tick); clearInterval(tapTimer); area.innerHTML='<div style="text-align:center;padding-top:100px;font-size:18px;">Time!</div>'; setHs('tap',tapScore); document.getElementById('tapHs').textContent=hs('tap'); return; }
        },1000);
        function spawn(){
            if(time<=0)return;
            const t=document.createElement('div');
            t.style.cssText='position:absolute;width:50px;height:50px;border-radius:50%;background:linear-gradient(135deg,#34d399,#60a5fa);cursor:pointer;left:'+(Math.random()*80)+'%;top:'+(Math.random()*70)+'%;';
            t.onclick=()=>{ tapScore++; document.getElementById('tapScore').textContent=tapScore; t.remove(); spawn(); };
            area.appendChild(t);
            setTimeout(()=>t.remove(),900);
        }
        tapTimer=setInterval(spawn,700); spawn();
    }

    // Snake
    function initSnake(){
        const c=document.getElementById('snakeCanvas'); const ctx=c.getContext('2d');
        let snake=[{x:10,y:10}], dir={x:1,y:0}, food={x:15,y:15}, score=0, alive=true;
        function draw(){
            ctx.fillStyle='#0f172a'; ctx.fillRect(0,0,300,300);
            ctx.fillStyle='#34d399'; snake.forEach(s=>ctx.fillRect(s.x*15,s.y*15,14,14));
            ctx.fillStyle='#f472b6'; ctx.fillRect(food.x*15,food.y*15,14,14);
            ctx.fillStyle='#fff'; ctx.font='14px system-ui'; ctx.fillText(score,10,20);
        }
        function step(){
            if(!alive)return;
            const head={x:snake[0].x+dir.x, y:snake[0].y+dir.y};
            if(head.x<0||head.x>=20||head.y<0||head.y>=20||snake.some(s=>s.x===head.x&&s.y===head.y)){ alive=false; setHs('snake',score); document.getElementById('snakeHs').textContent=hs('snake'); return; }
            snake.unshift(head);
            if(head.x===food.x&&head.y===food.y){ score++; food={x:Math.floor(Math.random()*20),y:Math.floor(Math.random()*20)}; }
            else snake.pop();
            draw();
        }
        document.onkeydown=e=>{
            if(e.key==='ArrowUp'&&dir.y===0)dir={x:0,y:-1};
            if(e.key==='ArrowDown'&&dir.y===0)dir={x:0,y:1};
            if(e.key==='ArrowLeft'&&dir.x===0)dir={x:-1,y:0};
            if(e.key==='ArrowRight'&&dir.x===0)dir={x:1,y:0};
        };
        draw(); setInterval(step,120);
    }
    show('xoxo');
    </script>
    """
    return HTMLResponse(render_page("Games", body))

@app.get("/register", response_class=HTMLResponse)
def registration_form():
    body = """
    <div class="glass-panel" style="max-width:480px; margin:40px auto;">
        <h2>Register</h2>
        <p class="instruction-text">Enter your legal name and an 11-digit phone number starting with 0.</p>
        <form action="/submit-registration" method="post" enctype="multipart/form-data">
            <label>Full Legal Name</label>
            <input type="text" name="name" required maxlength="80">
            <label>Mobile Phone Number</label>
            <input type="text" name="phone" placeholder="e.g. 08031234567" required>
            <label>Precinct Sector (City)</label>
            <input type="text" name="city_manual" placeholder="e.g. osogbo" required>
            <label>Avatar Profile Picture (optional, max 2 MB)</label>
            <div style="display:flex; align-items:center; gap:15px; margin:8px 0;">
                <input type="file" id="picFile" name="profile_pic_file" accept="image/*" onchange="previewAvatar(this)" style="color:var(--text-muted); margin:0;">
                <img id="picPreview" src="#" style="display:none; width:50px; height:50px; border-radius:50%; object-fit:cover; border:2px solid var(--accent-blue);">
            </div>
            <label>Primary Music Platform</label>
            <select name="music_provider">
                <option value="">None / Skip</option>
                <option value="Spotify">Spotify</option>
                <option value="Apple Music">Apple Music</option>
                <option value="Audiomack">Audiomack</option>
            </select>
            <label>Track or Playlist URL</label>
            <input type="text" name="music_url" placeholder="https://open.spotify.com/track/...">
            <br><br>
            <button type="submit" class="btn btn-blue" style="width:100%;">Complete Registration</button>
        </form>
    </div>
    <script>
    function previewAvatar(input) {
        const preview = document.getElementById('picPreview');
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = e => { preview.src = e.target.result; preview.style.display = 'block'; };
            reader.readAsDataURL(input.files[0]);
        } else {
            preview.style.display = 'none';
        }
    }
    </script>
    """
    return HTMLResponse(render_page("Register", body))

@app.post("/submit-registration")
async def handle_registration(
    name: str = Form(...),
    phone: str = Form(...),
    city_manual: str = Form(...),
    music_provider: str = Form(""),
    music_url: str = Form(""),
    profile_pic_file: UploadFile = File(None),
):
    if len(name.strip()) < 2 or len(name) > 80:
        raise HTTPException(400, "Name must be between 2 and 80 characters")
    clean_p = clean_phone(phone)
    if len(clean_p) != 10:
        raise HTTPException(400, "Invalid phone number")

    geo = CITY_AUTOFILL_MAP.get(city_manual.lower().strip(), {
        "country": "Nigeria", "state": "Region", "lga": city_manual, "area": "General Grid"
    })

    saved_pic_path = ""
    if profile_pic_file and profile_pic_file.filename:
        ext = Path(profile_pic_file.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(400, "Unsupported image type")
        content = await profile_pic_file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "Image too large (max 2 MB)")
        filename = f"{clean_p}{ext}"
        filepath = UPLOAD_DIR / filename
        filepath.write_bytes(content)
        saved_pic_path = f"/static/profile_pics/{filename}"

    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO citizens
            (phone, name, country, state, city, lga, area, token, status, xp, profile_pic, music_provider, music_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'token', 'Pending', 100, ?, ?, ?)
        """, (
            clean_p, sanitize(name), geo["country"], geo["state"],
            sanitize(city_manual), geo["lga"], geo["area"],
            saved_pic_path, music_provider[:40], sanitize(music_url, 300)
        ))
        await conn.commit()
    logger.info("New registration: %s", clean_p)
    return RedirectResponse("/register/success", status_code=303)

@app.get("/register/success", response_class=HTMLResponse)
def register_success_page():
    body = """
    <div class="glass-panel" style="max-width:500px; margin:80px auto; text-align:center;">
        <div style="font-size:56px; margin-bottom:15px;">⏳</div>
        <h2>Registration Received</h2>
        <p style="color:var(--text-muted); line-height:1.6;">
            Your defense grid node has been logged. Access is restricted until verified by regional monitors.
        </p>
        <br>
        <a href="/" class="btn btn-blue" style="width:100%; box-sizing:border-box;">Return to Home</a>
    </div>
    """
    return HTMLResponse(render_page("Registration Success", body))

# ---------------------------------------------------------------------------
# Citizen portal
# ---------------------------------------------------------------------------
@app.get("/portal/login", response_class=HTMLResponse)
def citizen_login_page(error: Optional[str] = None):
    err_html = f'<p style="color:#ef4444;">{html.escape(error)}</p>' if error else ""
    body = f"""
    <div class="glass-panel" style="max-width:400px; margin:80px auto;">
        <h2>Sign In</h2>
        {err_html}
        <p class="instruction-text">Enter your registered phone number to establish a session.</p>
        <form action="/portal/auth" method="post">
            <label>Phone Number</label>
            <input type="text" name="phone" placeholder="e.g. 08031234567" required>
            <br><br>
            <button type="submit" class="btn btn-blue" style="width:100%;">Sign In</button>
        </form>
    </div>
    """
    return HTMLResponse(render_page("Sign In", body))

@app.post("/portal/auth")
async def citizen_authentication(phone: str = Form(...)):
    target = clean_phone(phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (target,)) as c:
            citizen = await c.fetchone()
    if not citizen:
        return RedirectResponse("/portal/login?error=Phone+number+unrecognized", status_code=303)
    if citizen["status"] == "Pending":
        return HTMLResponse(render_page("Pending", "<h3 style='text-align:center;'>Clearance pending agency approval.</h3>"))
    if citizen["status"] == "Deleted":
        return RedirectResponse("/portal/login?error=Account+disabled", status_code=303)

    resp = RedirectResponse("/portal/feed", status_code=303)
    resp.set_cookie(key="citizen_session", value=sign_cookie_value(target), httponly=True, samesite="lax")
    return resp

@app.get("/portal/logout")
def handle_logout():
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie("citizen_session")
    return r

@app.get("/portal/citizen/{phone}", response_class=HTMLResponse)
async def view_citizen_profile(phone: str, current_user: dict = Depends(get_current_citizen)):
    target = clean_phone(phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute(
            "UPDATE direct_messages SET status = 'Read' WHERE sender = ? AND receiver = ? AND status = 'Active'",
            (target, current_user["phone"])
        )
        await conn.commit()

        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (target,)) as c:
            profile = await c.fetchone()
        if not profile:
            body = """
            <div class="glass-panel" style="max-width:450px; margin:40px auto; text-align:center;">
                <h3>Unregistered Terminal</h3>
                <p style="color:var(--text-muted);">Subscriber number does not exist.</p>
                <br><a href="/portal/feed" class="btn btn-blue">Return to Feed</a>
            </div>
            """
            return HTMLResponse(render_page("Not Found", body))

        async with conn.execute(
            "SELECT status FROM trust_network WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)",
            (current_user["phone"], target, target, current_user["phone"])
        ) as tn:
            relationship = await tn.fetchone()

        chat_html = ""
        if relationship and relationship["status"] == "Approved":
            async with conn.execute("""
                SELECT * FROM direct_messages
                WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?))
                AND status != 'Deleted'
                ORDER BY timestamp ASC
            """, (current_user["phone"], target, target, current_user["phone"])) as dm:
                messages = await dm.fetchall()

            msg_list = ""
            for m in messages:
                is_me = clean_phone(str(m["sender"])) == clean_phone(str(current_user["phone"]))
                align = "right" if is_me else "left"
                bg = "#1e3a8a" if is_me else "#1e293b"
                del_btn = (
                    f'<form action="/portal/chat/delete" method="post" style="display:inline; margin-left:8px;">'
                    f'<input type="hidden" name="msg_id" value="{m["id"]}">'
                    f'<input type="hidden" name="tgt_phone" value="{target}">'
                    f'<button type="submit" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:10px;">Delete</button></form>'
                )
                msg_list += (
                    f'<div style="margin-bottom:8px; text-align:{align};">'
                    f'<span style="background:{bg}; padding:6px 10px; border-radius:8px; display:inline-block; max-width:80%;">'
                    f'{m["message"]} {del_btn}</span></div>'
                )
            chat_html = f"""
            <div class="glass-panel" style="margin-top:20px; padding:15px; border-radius:12px;">
                <h4>Secure Chat <span class="badge badge-blue" style="padding:2px 6px; font-size:10px;">Active</span></h4>
                <div style="max-height:180px; overflow-y:auto; background:rgba(0,0,0,0.2); padding:10px; border-radius:8px; margin-bottom:10px;">
                    {msg_list or '<p style="font-size:12px; color:var(--text-muted); text-align:center;">No messages yet.</p>'}
                </div>
                <form action="/portal/chat/send" method="post" style="display:flex; gap:6px; margin:0;">
                    <input type="hidden" name="receiver_phone" value="{target}">
                    <input type="text" name="message" placeholder="Type a message..." required style="margin:0;">
                    <button type="submit" class="btn btn-blue" style="padding:0 14px;">Send</button>
                </form>
            </div>
            """

        if relationship and relationship["status"] == "Approved":
            rel_html = '<p style="color:var(--accent-emerald); font-weight:700;">Linked Trusted Peer</p>'
        elif relationship and relationship["status"] == "Pending":
            rel_html = '<p style="color:#fbbf24; font-style:italic;">Link request pending</p>'
        elif relationship and relationship["status"] == "Rejected":
            rel_html = '<p style="color:#f87171; font-style:italic;">Link request declined</p>'
        else:
            rel_html = (
                f'<form action="/portal/trust/request" method="post">'
                f'<input type="hidden" name="target_phone" value="{target}">'
                f'<button type="submit" class="btn btn-blue">Send Trust Request</button></form>'
            )

        avatar_src = profile["profile_pic"] or ""
        music_embed = generate_music_embed(profile["music_provider"], profile["music_url"])
        extra_css = """
        <style>
        body { background: radial-gradient(ellipse at 20% 10%, rgba(120, 100, 180, 0.12) 0%, transparent 50%),
                             radial-gradient(ellipse at 80% 80%, rgba(60, 140, 160, 0.1) 0%, transparent 50%),
                             #0a0e1a; }
        @keyframes softPulse { 0%,100% { opacity: 0.6; } 50% { opacity: 1; } }
        .profile-shell {
          max-width: 520px; margin: 50px auto;
          background: rgba(18, 24, 40, 0.75);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 28px;
          padding: 36px 32px;
          box-shadow: 0 20px 60px rgba(0,0,0,0.4), 0 0 40px rgba(100, 140, 200, 0.05);
          backdrop-filter: blur(12px);
        }
        .avatar-ring {
          width: 110px; height: 110px; margin: 0 auto 18px;
          border-radius: 50%;
          padding: 3px;
          background: linear-gradient(135deg, rgba(120,180,220,0.5), rgba(180,140,200,0.4));
          animation: softPulse 6s ease-in-out infinite;
        }
        .avatar-ring img, .avatar-ring div {
          width: 100%; height: 100%; border-radius: 50%; object-fit: cover;
          border: none; margin: 0;
        }
        .info-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 14px; }
        .info-row span:first-child { color: #94a3b8; }
        .info-row span:last-child { color: #e2e8f0; font-weight: 500; }
        .xp-pill { display: inline-block; background: rgba(16,185,129,0.12); color: #6ee7b7; padding: 4px 12px; border-radius: 999px; font-weight: 600; }
        </style>
        """
        if avatar_src:
            avatar_html = f'<div class="avatar-ring"><img src="{avatar_src}"></div>'
        else:
            initial = (profile["name"] or "?")[:1].upper()
            avatar_html = f'<div class="avatar-ring"><div style="background:linear-gradient(135deg,#3b82f6,#8b5cf6); display:flex; align-items:center; justify-content:center; font-weight:700; font-size:36px; color:white;">{initial}</div></div>'

        body = f"""
        <div class="profile-shell">
            {avatar_html}
            <h2 style="text-align:center; margin:0 0 6px; font-weight:700; letter-spacing:-0.3px;">Grid Node</h2>
            <p style="text-align:center; color:#64748b; font-size:13px; margin:0 0 22px;">Verified identity record</p>
            <div class="info-row"><span>Name</span><span>{html.escape(profile["name"] or "—")}</span></div>
            <div class="info-row"><span>City</span><span>{html.escape(profile["city"] or "—")}</span></div>
            <div class="info-row"><span>LGA</span><span>{html.escape(profile["lga"] or "—")}</span></div>
            <div class="info-row"><span>Area</span><span>{html.escape(profile["area"] or "—")}, {html.escape(profile["state"] or "")}</span></div>
            <div class="info-row"><span>Trust Score</span><span class="xp-pill">{profile["xp"]} XP</span></div>
            {f'<div style="margin-top:20px;">{music_embed}</div>' if music_embed else ""}
            <div style="margin-top:24px; text-align:center;">{rel_html if target != current_user["phone"] else ""}</div>
            {chat_html}
            <div style="margin-top:28px; display:grid; gap:10px;">
                {f'<a href="/portal/profile/edit" class="btn btn-blue" style="width:100%;">Edit Profile</a>' if target == current_user["phone"] else ""}
                <a href="/portal/feed" class="btn" style="width:100%; background:rgba(255,255,255,0.06); color:#cbd5e1;">Back to Feed</a>
            </div>
        </div>
        """
        return HTMLResponse(render_page(profile["name"], body, extra_css))

@app.get("/portal/profile/edit", response_class=HTMLResponse)
async def edit_profile_form(current_user: dict = Depends(get_current_citizen)):
    """Edit own profile. Name is locked."""
    body = f"""
    <div class="glass-panel" style="max-width:480px; margin:40px auto;">
        <h2>Edit Profile</h2>
        <p class="instruction-text">Name cannot be changed. Update your location, music, or avatar below.</p>
        <form action="/portal/profile/update" method="post" enctype="multipart/form-data">
            <label>Legal Name (locked)</label>
            <input type="text" value="{html.escape(current_user['name'] or '')}" disabled style="opacity:0.6; cursor:not-allowed;">
            <label>Precinct Sector (City)</label>
            <input type="text" name="city" value="{html.escape(current_user['city'] or '')}" required>
            <label>Assigned Area / Footprint</label>
            <input type="text" name="area" value="{html.escape(current_user['area'] or '')}">
            <label>State</label>
            <input type="text" name="state" value="{html.escape(current_user['state'] or '')}">
            <label>LGA</label>
            <input type="text" name="lga" value="{html.escape(current_user['lga'] or '')}">
            <label>Current Avatar</label>
            <div style="margin:8px 0;">
                {'<img src="' + current_user['profile_pic'] + '" style="width:60px; height:60px; border-radius:50%; object-fit:cover; border:2px solid var(--accent-blue);">' if current_user.get('profile_pic') else '<span style="color:var(--text-muted);">No avatar set</span>'}
            </div>
            <label>New Avatar (optional, max 2 MB)</label>
            <input type="file" name="profile_pic_file" accept="image/*" style="color:var(--text-muted);">
            <label>Music Platform</label>
            <select name="music_provider">
                <option value="" {'selected' if not current_user.get('music_provider') else ''}>None</option>
                <option value="Spotify" {'selected' if current_user.get('music_provider') == 'Spotify' else ''}>Spotify</option>
                <option value="Apple Music" {'selected' if current_user.get('music_provider') == 'Apple Music' else ''}>Apple Music</option>
                <option value="Audiomack" {'selected' if current_user.get('music_provider') == 'Audiomack' else ''}>Audiomack</option>
            </select>
            <label>Track or Playlist URL</label>
            <input type="text" name="music_url" value="{html.escape(current_user.get('music_url') or '')}" placeholder="https://...">
            <br><br>
            <button type="submit" class="btn btn-blue" style="width:100%;">Save Changes</button>
        </form>
        <br>
        <a href="/portal/citizen/{current_user['phone']}" class="btn" style="width:100%; background:rgba(255,255,255,0.05); color:#fff; box-sizing:border-box;">Cancel</a>
        <hr style="border:1px solid var(--border-glass); margin:30px 0;">
        <form action="/portal/profile/delete" method="post" onsubmit="return confirm('Permanently delete your account? This cannot be undone.');">
            <button type="submit" class="btn" style="width:100%; background:rgba(239,68,68,0.15); color:#f87171;">Delete My Account</button>
        </form>
    </div>
    """
    return HTMLResponse(render_page("Edit Profile", body))

@app.post("/portal/profile/update")
async def update_profile(
    city: str = Form(...),
    area: str = Form(""),
    state: str = Form(""),
    lga: str = Form(""),
    music_provider: str = Form(""),
    music_url: str = Form(""),
    profile_pic_file: UploadFile = File(None),
    current_user: dict = Depends(get_current_citizen),
):
    """Update editable profile fields. Name is never changed."""
    saved_pic = current_user.get("profile_pic") or ""
    if profile_pic_file and profile_pic_file.filename:
        ext = Path(profile_pic_file.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(400, "Unsupported image type")
        content = await profile_pic_file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, "Image too large (max 2 MB)")
        filename = f"{current_user['phone']}{ext}"
        (UPLOAD_DIR / filename).write_bytes(content)
        saved_pic = f"/static/profile_pics/{filename}"

    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("""
            UPDATE citizens
            SET city = ?, area = ?, state = ?, lga = ?,
                music_provider = ?, music_url = ?, profile_pic = ?
            WHERE phone = ?
        """, (
            sanitize(city, 60), sanitize(area, 80), sanitize(state, 40), sanitize(lga, 40),
            music_provider[:40], sanitize(music_url, 300), saved_pic,
            current_user["phone"]
        ))
        await conn.commit()
    logger.info("Profile updated: %s", current_user["phone"])
    return RedirectResponse(f"/portal/citizen/{current_user['phone']}", status_code=303)

@app.post("/portal/profile/delete")
async def delete_own_profile(current_user: dict = Depends(get_current_citizen)):
    """Soft-delete own account and log out."""
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE citizens SET status = 'Deleted' WHERE phone = ?", (current_user["phone"],))
        await conn.commit()
    logger.info("Account self-deleted: %s", current_user["phone"])
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("citizen_session")
    return resp

@app.post("/portal/chat/send")
async def send_direct_message(
    receiver_phone: str = Form(...),
    message: str = Form(...),
    current_user: dict = Depends(get_current_citizen),
):
    tgt = clean_phone(receiver_phone)
    text = sanitize(message, 1000)
    if not text:
        raise HTTPException(400, "Empty message")
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT status FROM trust_network WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)",
            (current_user["phone"], tgt, tgt, current_user["phone"])
        ) as tn:
            relationship = await tn.fetchone()
        if not relationship or relationship["status"] != "Approved":
            raise HTTPException(403, "Not trusted peers")
        await conn.execute(
            "INSERT INTO direct_messages (sender, receiver, message, status) VALUES (?, ?, ?, 'Active')",
            (current_user["phone"], tgt, text)
        )
        await conn.commit()
    return RedirectResponse(f"/portal/citizen/{tgt}", status_code=303)

@app.post("/portal/chat/delete")
async def delete_direct_message(
    msg_id: int = Form(...),
    tgt_phone: str = Form(...),
    current_user: dict = Depends(get_current_citizen),
):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "UPDATE direct_messages SET status = 'Deleted' WHERE id = ? AND (sender = ? OR receiver = ?)",
            (msg_id, current_user["phone"], current_user["phone"])
        )
        await conn.commit()
    return RedirectResponse(f"/portal/citizen/{clean_phone(tgt_phone)}", status_code=303)

# ---------------------------------------------------------------------------
# Feed & posts
# ---------------------------------------------------------------------------
@app.post("/portal/viral/post")
async def post_viral_broadcast(
    context: str = Form(...),
    visibility: str = Form("Public"),
    current_user: dict = Depends(get_current_citizen),
):
    text = sanitize(context, 250)
    if not text:
        raise HTTPException(400, "Empty broadcast")
    if visibility not in ("Public", "Private"):
        visibility = "Public"
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "INSERT INTO viral_posts (author, phone, context, status, visibility) VALUES (?, ?, ?, 'Pending', ?)",
            (current_user["name"], current_user["phone"], text, visibility)
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.get("/portal/feed", response_class=HTMLResponse)
async def user_portal_feed(current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row

        async with conn.execute("""
            SELECT name, phone, profile_pic FROM citizens WHERE phone IN (
                SELECT sender FROM trust_network WHERE receiver = ? AND status = 'Approved'
                UNION
                SELECT receiver FROM trust_network WHERE sender = ? AND status = 'Approved'
            )
        """, (current_user["phone"], current_user["phone"])) as cx:
            neighbors = await cx.fetchall()
        trusted_phones = {clean_phone(str(n["phone"])) for n in neighbors}

        async with conn.execute(
            "SELECT sender FROM direct_messages WHERE receiver = ? AND status = 'Active'",
            (current_user["phone"],)
        ) as dm_check:
            unread_rows = await dm_check.fetchall()
            senders_with_messages = {clean_phone(str(r["sender"])) for r in unread_rows}

        neighbors_html = ""
        for n in neighbors:
            avatar_block = (
                f'<img src="{n["profile_pic"]}" style="width:36px; height:36px; border-radius:50%; object-fit:cover;">'
                if n["profile_pic"] else
                f'<div style="width:36px; height:36px; border-radius:50%; background:#3b82f6; display:flex; align-items:center; justify-content:center; font-weight:bold; color:#fff;">{(n["name"] or "?")[:1].upper()}</div>'
            )
            envelope = '<span class="retro-envelope" title="New message"></span>' if clean_phone(str(n["phone"])) in senders_with_messages else ""
            neighbors_html += f"""
            <div class="neighbor-item" data-search="{html.escape((n['name'] or '').lower())} {n['phone']}"
                 style="display:flex; align-items:center; gap:12px; padding:10px; background:rgba(255,255,255,0.02); border-radius:10px; margin-bottom:8px;">
                {avatar_block}
                <div style="flex-grow:1;">
                    <div style="font-size:14px; font-weight:700; display:flex; align-items:center; gap:8px;">
                        <a href="/portal/citizen/{n['phone']}" style="color:#60a5fa; text-decoration:none;">{html.escape(n['name'] or '')}</a>
                        {envelope}
                    </div>
                    <div style="font-size:11px; color:var(--text-muted);">Linked Peer</div>
                </div>
            </div>
            """

        async with conn.execute(
            "SELECT * FROM viral_posts WHERE status != 'Deleted' AND (status = 'Approved' OR phone = ?) ORDER BY id DESC",
            (current_user["phone"],)
        ) as c:
            posts = await c.fetchall()

        feed_html = ""
        for p in posts:
            is_owner = clean_phone(str(p["phone"])) == clean_phone(str(current_user["phone"]))
            if not is_owner:
                if p["visibility"] == "Private":
                    continue
                if not (p["status"] in ("Approved", "Reported") and clean_phone(str(p["phone"])) in trusted_phones):
                    continue

            async with conn.execute("SELECT profile_pic, music_provider, music_url FROM citizens WHERE phone = ?", (p["phone"],)) as auth_info:
                author_meta = await auth_info.fetchone()
            p_avatar = (
                f'<img src="{author_meta["profile_pic"]}" style="width:28px; height:28px; border-radius:50%; object-fit:cover; vertical-align:middle; margin-right:6px;">'
                if author_meta and author_meta["profile_pic"] else ""
            )
            p_music = generate_music_embed(author_meta["music_provider"], author_meta["music_url"]) if author_meta else ""

            async with conn.execute(
                "SELECT * FROM viral_comments WHERE post_id = ? AND status != 'Deleted' ORDER BY id ASC",
                (p["id"],)
            ) as cc:
                comments = await cc.fetchall()
            cm_html = ""
            for cmt in comments:
                rep_btn = (
                    f'<form action="/portal/viral/comment/report" method="post" style="display:inline; margin-left:6px;">'
                    f'<input type="hidden" name="comment_id" value="{cmt["id"]}">'
                    f'<button type="submit" style="background:none; border:none; color:#f87171; opacity:0.6; cursor:pointer; font-size:11px; padding:0;">⚠️</button></form>'
                    if cmt["phone"] != current_user["phone"] else ""
                )
                cm_html += (
                    f'<div class="comment-box"><b><a href="/portal/citizen/{cmt["phone"]}" style="color:#60a5fa; text-decoration:none;">'
                    f'{html.escape(cmt["author"] or "")}</a>:</b> {cmt["text"]} {rep_btn}</div>'
                )

            badge = '<span class="badge badge-blue">Verified Broadcast</span>'
            if p["status"] == "Pending":
                badge = '<span class="badge badge-amber">Awaiting Verification</span>'
            elif p["status"] == "Reported":
                badge = '<span class="badge" style="background:rgba(239,68,68,0.15); color:#f87171;">Flagged</span>'
            vis_badge = f' <span class="badge" style="background:rgba(255,255,255,0.1); color:#fff;">{p["visibility"]}</span>'

            mgmt_actions = ""
            if is_owner:
                next_vis = "Private" if p["visibility"] == "Public" else "Public"
                mgmt_actions = f"""
                <div style="margin-top:10px; display:flex; gap:10px;">
                    <form action="/portal/viral/post/toggle-visibility" method="post" style="margin:0;">
                        <input type="hidden" name="post_id" value="{p['id']}">
                        <input type="hidden" name="visibility" value="{next_vis}">
                        <button type="submit" class="btn" style="padding:4px 10px; font-size:12px; background:#475569; color:#fff;">Make {next_vis}</button>
                    </form>
                    <form action="/portal/viral/post/delete" method="post" style="margin:0;">
                        <input type="hidden" name="post_id" value="{p['id']}">
                        <button type="submit" class="btn" style="padding:4px 10px; font-size:12px; background:#ef4444; color:#fff;">Delete</button>
                    </form>
                </div>
                """
            rep_p_btn = (
                f'<form action="/portal/viral/post/report" method="post" style="display:inline-block; margin-left:8px;">'
                f'<input type="hidden" name="post_id" value="{p["id"]}">'
                f'<button type="submit" title="Report" style="background:none; border:none; color:#f87171; opacity:0.6; cursor:pointer; font-size:12px; padding:0;">⚠️</button></form>'
                if p["phone"] != current_user["phone"] and p["status"] != "Reported" else ""
            )

            feed_html += f"""
            <div class="glass-panel" style="margin-bottom:16px; padding:20px;">
                <h4>{p_avatar} <a href="/portal/citizen/{p['phone']}" style="color:#fff; text-decoration:none;">{html.escape(p['author'] or '')}</a> {badge}{vis_badge} {rep_p_btn}</h4>
                <p>"{p['context']}"</p>
                {f'<div style="margin:8px 0;">{p_music}</div>' if p_music else ''}
                {mgmt_actions}
                <div style="margin-top:12px; border-top:1px solid var(--border-glass); padding-top:10px;">
                    {cm_html or '<p style="font-size:12px; color:var(--text-muted); font-style:italic;">No comments yet.</p>'}
                    <form action="/portal/viral/comment" method="post" style="margin-top:8px; display:flex; gap:6px;">
                        <input type="hidden" name="post_id" value="{p['id']}">
                        <input type="text" name="text" placeholder="Reply..." required style="margin:0;">
                        <button type="submit" class="btn btn-blue" style="padding:4px 12px; font-size:12px;">Reply</button>
                    </form>
                </div>
            </div>
            """

        async with conn.execute(
            "SELECT t.id, c.name, t.sender FROM trust_network t JOIN citizens c ON t.sender = c.phone WHERE t.receiver = ? AND t.status = 'Pending'",
            (current_user["phone"],)
        ) as tx:
            incoming_reqs = await tx.fetchall()
        async with conn.execute(
            "SELECT t.id, c.name, t.receiver FROM trust_network t JOIN citizens c ON t.receiver = c.phone WHERE t.sender = ? AND t.status = 'Pending'",
            (current_user["phone"],)
        ) as ty:
            outgoing_reqs = await ty.fetchall()

        req_html = "".join(
            f"""<div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:5px; background:rgba(255,255,255,0.01); padding:5px; border-radius:6px;">
                <span style="font-size:13px;">{html.escape(r['name'] or '')}</span>
                <div style="display:flex; gap:4px;">
                    <form action="/portal/trust/accept" method="post" style="margin:0;"><input type="hidden" name="request_id" value="{r['id']}"><button type="submit" class="btn btn-blue" style="padding:4px 8px; font-size:11px;">Accept</button></form>
                    <form action="/portal/trust/reject" method="post" style="margin:0;"><input type="hidden" name="request_id" value="{r['id']}"><button type="submit" class="btn" style="padding:4px 8px; font-size:11px; background:#ef4444; color:#fff;">Reject</button></form>
                </div>
            </div>""" for r in incoming_reqs
        )
        sent_html = "".join(f'<div style="font-size:13px; color:var(--text-muted); margin-bottom:4px;">Request sent to {html.escape(r["name"] or "")}</div>' for r in outgoing_reqs)

    live_scripts = """
    <script>
    function filterNeighbors(val) {
        const text = val.toLowerCase().trim();
        document.querySelectorAll('.neighbor-item').forEach(item => {
            const searchSpace = item.getAttribute('data-search') || '';
            item.style.display = searchSpace.includes(text) ? 'flex' : 'none';
        });
    }
    function updateCounter(textarea) {
        const count = textarea.value.length;
        const display = document.getElementById('charCount');
        display.innerText = count + ' / 250';
        display.style.color = count > 250 ? '#ef4444' : 'var(--text-muted)';
    }
    </script>
    """
    body = f"""
    <div style="max-width:900px; margin:0 auto; display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
            <div class="glass-panel" style="margin-bottom:20px;">
                <h3>Welcome, <a href="/portal/citizen/{current_user['phone']}" style="color:var(--accent-blue); text-decoration:underline;">{html.escape(current_user['name'] or '')}</a></h3>
                <p class="instruction-text">Share an update. It remains private until approved by regional monitors.</p>
                <form action="/portal/viral/post" method="post">
                    <textarea name="context" maxlength="250" oninput="updateCounter(this)" style="width:100%; height:60px; background:#090d16; color:#fff; margin-bottom:2px;" placeholder="What is happening..." required></textarea>
                    <div id="charCount" style="text-align:right; font-size:11px; color:var(--text-muted); margin-bottom:10px;">0 / 250</div>
                    <label>Broadcast Visibility</label>
                    <select name="visibility" style="margin-top:5px;">
                        <option value="Public">Public (Trusted peers can view)</option>
                        <option value="Private">Private (Only you)</option>
                    </select>
                    <br>
                    <button type="submit" class="btn btn-blue" style="width:100%; margin-top:5px;">Submit Broadcast</button>
                </form>
            </div>
            <h3>Broadcast Stream</h3>
            {feed_html or '<p style="color:var(--text-muted); font-style:italic;">No dispatches available.</p>'}
        </div>
        <div>
            <div class="glass-panel" style="margin-bottom:20px;">
                <h3>Trusted Neighbors ({len(neighbors)})</h3>
                <input type="text" placeholder="Search peers..." onkeyup="filterNeighbors(this.value)" style="margin-bottom:12px; padding:8px 12px; font-size:13px;">
                <div style="max-height:220px; overflow-y:auto;">{neighbors_html or '<p style="color:var(--text-muted); font-size:12px; font-style:italic;">No connected peers.</p>'}</div>
            </div>
            <div class="glass-panel" style="margin-bottom:20px;">
                <h3>Trust Network</h3>
                <form action="/portal/trust/lookup" method="post" style="display:flex; gap:8px;">
                    <input type="text" name="target_phone" placeholder="Lookup phone..." required style="margin:0;">
                    <button type="submit" class="btn btn-blue" style="padding:0 12px;">Search</button>
                </form>
                <div style="margin-top:15px;"><h5>Incoming Requests</h5>{req_html or '<p style="color:var(--text-muted); font-size:12px;">None</p>'}</div>
                <div style="margin-top:15px;"><h5>Outgoing</h5>{sent_html or '<p style="color:var(--text-muted); font-size:12px;">None</p>'}</div>
            </div>
            <center><a href="/portal/logout" class="btn" style="background:rgba(239,68,68,0.15); color:#f87171; width:100%;">Disconnect</a></center>
        </div>
    </div>
    """
    return HTMLResponse(render_page("Feed", body, live_scripts))

@app.post("/portal/viral/post/toggle-visibility")
async def toggle_post_visibility(
    post_id: int = Form(...),
    visibility: str = Form(...),
    current_user: dict = Depends(get_current_citizen),
):
    if visibility not in ("Public", "Private"):
        raise HTTPException(400, "Invalid visibility")
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "UPDATE viral_posts SET visibility = ? WHERE id = ? AND phone = ?",
            (visibility, post_id, current_user["phone"])
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/viral/post/delete")
async def delete_post(post_id: int = Form(...), current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "UPDATE viral_posts SET status = 'Deleted' WHERE id = ? AND phone = ?",
            (post_id, current_user["phone"])
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/viral/post/report")
async def report_post(post_id: int = Form(...), current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET status = 'Reported' WHERE id = ?", (post_id,))
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/viral/comment")
async def comment_viral_post(
    post_id: int = Form(...),
    text: str = Form(...),
    current_user: dict = Depends(get_current_citizen),
):
    clean_text = sanitize(text, 400)
    if not clean_text:
        raise HTTPException(400, "Empty comment")
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "INSERT INTO viral_comments (post_id, author, phone, text, status) VALUES (?, ?, ?, ?, 'Approved')",
            (post_id, current_user["name"], current_user["phone"], clean_text)
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/viral/comment/report")
async def report_viral_comment(comment_id: int = Form(...), current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_comments SET status = 'Reported' WHERE id = ?", (comment_id,))
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

# ---------------------------------------------------------------------------
# Trust network
# ---------------------------------------------------------------------------
@app.post("/portal/trust/lookup")
async def trust_profile_lookup(target_phone: str = Form(...), current_user: dict = Depends(get_current_citizen)):
    return RedirectResponse(f"/portal/citizen/{clean_phone(target_phone)}", status_code=303)

@app.post("/portal/trust/request")
async def send_trust_request(target_phone: str = Form(...), current_user: dict = Depends(get_current_citizen)):
    target = clean_phone(target_phone)
    if target == current_user["phone"]:
        raise HTTPException(400, "Cannot trust yourself")
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO trust_network (sender, receiver, status) VALUES (?, ?, 'Pending')",
            (current_user["phone"], target)
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/trust/accept")
async def accept_trust_request(request_id: int = Form(...), current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "UPDATE trust_network SET status = 'Approved' WHERE id = ? AND receiver = ?",
            (request_id, current_user["phone"])
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

@app.post("/portal/trust/reject")
async def reject_trust_request(request_id: int = Form(...), current_user: dict = Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute(
            "UPDATE trust_network SET status = 'Rejected' WHERE id = ? AND receiver = ?",
            (request_id, current_user["phone"])
        )
        await conn.commit()
    return RedirectResponse("/portal/feed", status_code=303)

# ---------------------------------------------------------------------------
# Admin (protected)
# ---------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(key: Optional[str] = None, admin_key: Optional[str] = Cookie(None)):
    if (key or admin_key) != ADMIN_KEY:
        body = """
        <div class="glass-panel" style="max-width:400px; margin:80px auto; text-align:center;">
            <h2>Admin Access</h2>
            <p class="instruction-text">Enter the admin key to open the control matrix.</p>
            <form method="get">
                <input type="password" name="key" placeholder="Admin key" required>
                <button type="submit" class="btn btn-blue" style="width:100%; margin-top:10px;">Unlock</button>
            </form>
        </div>
        """
        return HTMLResponse(render_page("Admin Login", body))

    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE status != 'Deleted' ORDER BY name") as c1:
            all_users = await c1.fetchall()
        async with conn.execute("SELECT * FROM viral_posts WHERE status IN ('Pending', 'Reported') ORDER BY id DESC") as c2:
            pending_posts = await c2.fetchall()
        async with conn.execute("SELECT * FROM viral_comments WHERE status = 'Reported' ORDER BY id DESC") as c3:
            reported_comments = await c3.fetchall()
        async with conn.execute("SELECT * FROM direct_messages WHERE status = 'Active' ORDER BY id DESC LIMIT 50") as c4:
            active_dms = await c4.fetchall()
        async with conn.execute("SELECT COUNT(*) as n FROM citizens WHERE status = 'Approved'") as cx:
            approved_count = (await cx.fetchone())["n"]
        async with conn.execute("SELECT COUNT(*) as n FROM citizens WHERE status = 'Pending'") as cy:
            pending_users = (await cy.fetchone())["n"]

    total_users = len(all_users)
    pending_post_count = len(pending_posts)
    reported_count = len(reported_comments)
    dm_count = len(active_dms)

    def status_badge(status: str) -> str:
        s = (status or "").lower()
        if s == "approved":
            return '<span class="badge badge-green">Approved</span>'
        if s == "pending":
            return '<span class="badge badge-amber">Pending</span>'
        if s == "reported":
            return '<span class="badge badge-red">Reported</span>'
        return f'<span class="badge badge-gray">{html.escape(status or "—")}</span>'

    def user_row(u):
        approve = (
            f'<form action="/admin/approve-citizen" method="post" style="display:inline;">'
            f'<input type="hidden" name="phone" value="{u["phone"]}"><input type="hidden" name="key" value="{ADMIN_KEY}">'
            f'<button type="submit" class="btn btn-sm btn-success">Approve</button></form>'
            if u["status"] == "Pending" else ""
        )
        return (
            f"<tr>"
            f"<td><strong>{html.escape(u['name'] or '—')}</strong></td>"
            f"<td>0{u['phone']}</td>"
            f"<td>{status_badge(u['status'])}</td>"
            f"<td style='font-size:12px; color:var(--text-muted);'>{html.escape(u['city'] or '')}</td>"
            f"<td class='action-group'>{approve}"
            f'<form action="/admin/delete-citizen" method="post" style="display:inline;">'
            f'<input type="hidden" name="phone" value="{u["phone"]}"><input type="hidden" name="key" value="{ADMIN_KEY}">'
            f'<button type="submit" class="btn btn-sm btn-danger">Purge</button></form></td>'
            f"</tr>"
        )

    u_rows = "".join(user_row(u) for u in all_users) or '<tr><td colspan="5" class="empty-state">No citizens registered.</td></tr>'

    p_rows = ""
    for p in pending_posts:
        p_rows += (
            f"<tr>"
            f"<td>{status_badge(p['status'])}</td>"
            f"<td><strong>{html.escape(p['author'] or '')}</strong><br><span style='font-size:12px; color:var(--text-muted);'>0{p['phone']}</span></td>"
            f"<td style='max-width:360px;'>{html.escape(p['context'] or '')}<br><span style='font-size:11px; color:var(--text-muted);'>{p['visibility']} · {p['timestamp'] or ''}</span></td>"
            f"<td class='action-group'>"
            f"<form action='/admin/approve-post' method='post'><input type='hidden' name='id' value='{p['id']}'><input type='hidden' name='key' value='{ADMIN_KEY}'><button type='submit' class='btn btn-sm btn-success'>Approve</button></form>"
            f"<form action='/admin/delete-post' method='post'><input type='hidden' name='id' value='{p['id']}'><input type='hidden' name='key' value='{ADMIN_KEY}'><button type='submit' class='btn btn-sm btn-danger'>Delete</button></form>"
            f"</td></tr>"
        )
    p_rows = p_rows or '<tr><td colspan="4" class="empty-state">No posts awaiting moderation.</td></tr>'

    c_rows = "".join(
        f"""<tr>
            <td><strong>{html.escape(c['author'] or '')}</strong><br><span style="font-size:12px; color:var(--text-muted);">Post #{c['post_id']}</span></td>
            <td style="max-width:400px;">{html.escape(c['text'] or '')}<br><span style="font-size:11px; color:var(--text-muted);">{c['timestamp'] or ''}</span></td>
            <td class="action-group">
                <form action="/admin/approve-comment" method="post"><input type="hidden" name="id" value="{c['id']}"><input type="hidden" name="key" value="{ADMIN_KEY}"><button type="submit" class="btn btn-sm btn-success">Dismiss</button></form>
                <form action="/admin/delete-comment" method="post"><input type="hidden" name="id" value="{c['id']}"><input type="hidden" name="key" value="{ADMIN_KEY}"><button type="submit" class="btn btn-sm btn-danger">Delete</button></form>
            </td>
        </tr>""" for c in reported_comments
    ) or '<tr><td colspan="3" class="empty-state">No reported comments.</td></tr>'

    m_rows = "".join(
        f"""<tr>
            <td>0{m['sender']} → 0{m['receiver']}</td>
            <td style="max-width:420px;">{html.escape(m['message'] or '')}<br><span style="font-size:11px; color:var(--text-muted);">{m['timestamp'] or ''}</span></td>
            <td>
                <form action="/admin/delete-message" method="post">
                    <input type="hidden" name="id" value="{m['id']}">
                    <input type="hidden" name="key" value="{ADMIN_KEY}">
                    <button type="submit" class="btn btn-sm btn-danger">Delete</button>
                </form>
            </td>
        </tr>""" for m in active_dms
    ) or '<tr><td colspan="3" class="empty-state">No active messages.</td></tr>'

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    body = f"""
    <div style="max-width:1000px; margin:0 auto; padding-top:10px;">
        <div class="dash-header">
            <div>
                <h2 style="margin:0 0 4px 0;">Regional Control Panel</h2>
                <p style="margin:0; color:var(--text-muted); font-size:13px;">OmniWatch Civil Defense Network · Last refreshed {now}</p>
            </div>
            <a href="/" class="btn" style="background:rgba(255,255,255,0.06); color:#cbd5e1; padding:10px 16px;">← Return Home</a>
        </div>

        <div class="stats-grid">
            <div class="stat-card"><div class="value">{total_users}</div><div class="label">Total Citizens</div></div>
            <div class="stat-card"><div class="value" style="color:#34d399;">{approved_count}</div><div class="label">Approved</div></div>
            <div class="stat-card"><div class="value" style="color:#fbbf24;">{pending_users}</div><div class="label">Pending Users</div></div>
            <div class="stat-card"><div class="value" style="color:#60a5fa;">{pending_post_count}</div><div class="label">Posts to Review</div></div>
            <div class="stat-card"><div class="value" style="color:#f87171;">{reported_count}</div><div class="label">Reported Comments</div></div>
            <div class="stat-card"><div class="value">{dm_count}</div><div class="label">Active Messages</div></div>
        </div>

        <div class="glass-panel" style="margin-bottom:24px;">
            <h3 style="margin-top:0;">Registered Citizens</h3>
            <input type="text" id="userSearch" class="search-bar" placeholder="Filter by name or phone…" onkeyup="filterTable('userSearch','usersTable')">
            <div class="table-wrap">
                <table class="admin-table" id="usersTable">
                    <thead><tr><th>Name</th><th>Phone</th><th>Status</th><th>City</th><th>Actions</th></tr></thead>
                    <tbody>{u_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="glass-panel" style="margin-bottom:24px;">
            <h3 style="margin-top:0;">Broadcast Moderation</h3>
            <div class="table-wrap">
                <table class="admin-table">
                    <thead><tr><th>Status</th><th>Author</th><th>Content</th><th>Actions</th></tr></thead>
                    <tbody>{p_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="glass-panel" style="margin-bottom:24px;">
            <h3 style="margin-top:0;">Reported Comments</h3>
            <div class="table-wrap">
                <table class="admin-table">
                    <thead><tr><th>Author</th><th>Comment</th><th>Actions</th></tr></thead>
                    <tbody>{c_rows}</tbody>
                </table>
            </div>
        </div>

        <div class="glass-panel">
            <h3 style="margin-top:0;">Live Chat Monitor <span style="font-weight:400; color:var(--text-muted); font-size:14px;">(latest 50)</span></h3>
            <div class="table-wrap">
                <table class="admin-table">
                    <thead><tr><th>Route</th><th>Message</th><th>Action</th></tr></thead>
                    <tbody>{m_rows}</tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
    function filterTable(inputId, tableId) {{
        const q = document.getElementById(inputId).value.toLowerCase();
        const rows = document.querySelectorAll('#' + tableId + ' tbody tr');
        rows.forEach(row => {{
            const text = row.innerText.toLowerCase();
            row.style.display = text.includes(q) ? '' : 'none';
        }});
    }}
    </script>
    """
    resp = HTMLResponse(render_page("Dashboard", body))
    resp.set_cookie("admin_key", ADMIN_KEY, httponly=True, samesite="lax")
    return resp

def _check_admin(key: Optional[str]) -> None:
    if key != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")

@app.post("/admin/approve-citizen")
async def app_cit(phone: str = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE citizens SET status = 'Approved' WHERE phone = ?", (phone,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/delete-citizen")
async def del_cit(phone: str = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE citizens SET status = 'Deleted' WHERE phone = ?", (phone,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/approve-post")
async def app_pos(id: int = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET status = 'Approved' WHERE id = ?", (id,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/delete-post")
async def del_pos(id: int = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET status = 'Deleted' WHERE id = ?", (id,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/approve-comment")
async def app_cmt(id: int = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_comments SET status = 'Approved' WHERE id = ?", (id,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/delete-comment")
async def del_cmt(id: int = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_comments SET status = 'Deleted' WHERE id = ?", (id,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

@app.post("/admin/delete-message")
async def del_msg(id: int = Form(...), key: str = Form(...)):
    _check_admin(key)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE direct_messages SET status = 'Deleted' WHERE id = ?", (id,))
        await conn.commit()
    return RedirectResponse(f"/dashboard?key={ADMIN_KEY}", status_code=303)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=4444, reload=True)
