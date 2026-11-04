import os, hmac, hashlib, html, aiosqlite, shutil, datetime
from typing import Optional
from fastapi import FastAPI, Form, Response, Depends, HTTPException, Cookie, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

COOKIE_SIGNING_KEY = os.getenv("COOKIE_SECRET_KEY", "grid-security-core-token-991").encode()
DB_FILE = "omni_matrix_final.db"
UPLOAD_DIR = "static/profile_pics"
BACKUP_DIR = "backups"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

CITY_AUTOFILL_MAP = {
    "osogbo": {"country": "Nigeria", "state": "Osun", "lga": "Osogbo", "area": "Ataoja Sector"},
    "ile-ife": {"country": "Nigeria", "state": "Osun", "lga": "Ile-Ife", "area": "Ife Central Town"},
    "ibadan": {"country": "Nigeria", "state": "Oyo", "lga": "Ibadan", "area": "Ido Sector Grid"},
    "ogbomoso": {"country": "Nigeria", "state": "Oyo", "lga": "Ogbomoso", "area": "Ogbomoso South Central"}
}

SOCIAL_FOOTER_HTML = """<footer style="margin-top:40px; text-align:center; padding:20px; border-top:1px solid var(--border-glass);"><div style="display:flex; justify-content:center; gap:15px; font-size:13px;"><a href="https://x.com" target="_blank" style="color:#3b82f6; text-decoration:none; font-weight:700;">Twitter</a> <a href="https://facebook.com" target="_blank" style="color:#3b82f6; text-decoration:none; font-weight:700;">Facebook</a> <a href="https://whatsapp.com" target="_blank" style="color:#10b981; text-decoration:none; font-weight:700;">WhatsApp</a></div></footer>"""
UPGRADED_CSS = """:root { --bg-slate: #020617; --panel-glass: rgba(15, 23, 42, 0.8); --border-glass: rgba(255, 255, 255, 0.08); --accent-emerald: #10b981; --accent-blue: #3b82f6; --text-main: #f8fafc; --text-muted: #94a3b8; } body { font-family: system-ui, sans-serif; background: radial-gradient(circle at 50% 0%, #0f172a 0%, #020617 80%); color: var(--text-main); margin: 0; padding: 20px; padding-bottom:120px; } .glass-panel { background: var(--panel-glass); border: 1px solid var(--border-glass); border-radius: 24px; padding: 30px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6); } .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; text-transform: uppercase; } .badge-blue { background: rgba(59, 130, 246, 0.15); color: #60a5fa; display: inline-block; } .badge-amber { background: rgba(245, 158, 11, 0.15); color: #fbbf24; display: inline-block; } .btn { display: inline-flex; align-items: center; justify-content: center; padding: 14px 20px; border-radius: 12px; font-weight: 700; text-decoration: none; border: none; cursor: pointer; font-size:14px; } .btn-blue { background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; } input[type='text'], select, textarea { width: 100%; padding: 12px; background: #090d16; border: 1px solid var(--border-glass); color: white; border-radius: 10px; box-sizing: border-box; margin-top: 4px; margin-bottom: 10px; } label { color: var(--text-muted); font-size: 13px; font-weight: 600; } .comment-box { background: rgba(255,255,255,0.03); padding: 8px; border-radius: 6px; margin-top: 6px; font-size: 13px; text-align: left; border-left: 2px solid var(--accent-blue); } .instruction-text { background:rgba(59,130,246,0.06); border-left:3px solid var(--accent-blue); padding:10px; border-radius:6px; font-size:13px; color:#cbd5e1; text-align:left; margin-bottom:15px; } .retro-envelope { width: 22px; height: 14px; background: #fffdf6; border: 1px solid #7f1d1d; position: relative; display: inline-block; box-shadow: 1px 2px 4px rgba(0,0,0,0.4); border-image: repeating-linear-gradient(45deg, #ef4444, #ef4444 4px, #fff 4px, #fff 8px, #3b82f6 8px, #3b82f6 12px, #fff 12px, #fff 16px) 2; }"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.path.exists(DB_FILE):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(DB_FILE, os.path.join(BACKUP_DIR, f"backup_{timestamp}.db"))
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS citizens (
                phone TEXT PRIMARY KEY, name TEXT, country TEXT, state TEXT, 
                city TEXT, lga TEXT, area TEXT, token TEXT, status TEXT, xp INTEGER DEFAULT 100,
                profile_pic TEXT DEFAULT '', music_provider TEXT DEFAULT '', music_url TEXT DEFAULT ''
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS viral_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                author TEXT, phone TEXT, context TEXT, status TEXT, reshares INTEGER DEFAULT 0,
                visibility TEXT DEFAULT 'Public'
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS viral_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, 
                author TEXT, phone TEXT, text TEXT, status TEXT DEFAULT 'Approved', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trust_network (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, status TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS direct_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, message TEXT, 
                status TEXT DEFAULT 'Active', timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        try: await conn.execute("ALTER TABLE viral_posts ADD COLUMN visibility TEXT DEFAULT 'Public';")
        except: pass
        try: await conn.execute("ALTER TABLE direct_messages ADD COLUMN status TEXT DEFAULT 'Active';")
        except: pass
        await conn.execute("""
            INSERT OR IGNORE INTO citizens (phone, name, country, state, city, lga, area, token, status, xp, profile_pic, music_provider, music_url)
            VALUES ('8031112225', 'Officer Adewale', 'Nigeria', 'Osun', 'Osogbo', 'Osogbo', 'Ataoja Sector', 'm1', 'Approved', 450, '', '', '')
        """)
        await conn.commit()
    yield

app = FastAPI(title="OmniWatch Civil Defense Network", version="1.2.5", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

def clean_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("234") and len(digits) > 10: digits = digits[3:]
    elif digits.startswith("0") and len(digits) == 11: digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits

def sanitize(text: str) -> str: return html.escape(text.strip())
def sign_cookie_value(value: str) -> str: return f"{value}.{hmac.new(COOKIE_SIGNING_KEY, value.encode(), hashlib.sha256).hexdigest()}"
def verify_cookie_value(signed_value: Optional[str]) -> Optional[str]:
    if not signed_value or "." not in signed_value: return None
    value, signature = signed_value.rsplit(".", 1)
    expected = hmac.new(COOKIE_SIGNING_KEY, value.encode(), hashlib.sha256).hexdigest()
    return value if hmac.compare_digest(signature, expected) else None
async def get_current_citizen(citizen_session: Optional[str] = Cookie(None)):
    verified = verify_cookie_value(citizen_session)
    if not verified: raise HTTPException(status_code=401, detail="Unauthorized Matrix Access")
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (verified,)) as c:
            row = await c.fetchone()
            if not row: raise HTTPException(status_code=401, detail="Terminal Unrecognized")
            return dict(row)
def generate_music_embed(provider: str, url: str) -> str:
    if not url: return ""
    try:
        url = url.strip()
        if "spotify.com" in url.lower():
            embed_url = url.replace("/track/", "/embed/track/").replace("/playlist/", "/embed/playlist/").replace("/album/", "/embed/album/")
            return f'<iframe src="{embed_url}" width="100%" height="152" frameborder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" style="border-radius:12px; margin-top:10px;" loading="lazy"></iframe>'
        elif "apple.com" in url.lower():
            embed_url = url.replace("://apple.com", "embed.://apple.com")
            return f'<iframe src="{embed_url}" width="100%" height="175" frameborder="0" allow="autoplay *; encrypted-media *; fullscreen *" style="width:100%; max-width:660px; overflow:hidden; background:transparent; border-radius:12px; margin-top:10px;"></iframe>'
        elif "audiomack.com" in url.lower():
            embed_url = url.replace("audiomack.com", "://audiomack.com")
            return f'<iframe src="{embed_url}?background=1" scrolling="no" width="100%" height="250" frameborder="0" allowtransparency="true" allow="automated-media; encrypted-media" style="border-radius:12px; margin-top:10px;"></iframe>'
    except Exception: pass
    return f'<p style="font-size:11px; color:var(--text-muted); text-main">🎵 <a href="{html.escape(url)}" target="_blank" style="color:var(--accent-blue);">External Music Stream</a></p>'

@app.get("/favicon.ico", include_in_schema=False)
def favicon_fallback(): return Response(status_code=204)

@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def icon_fallback(): return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
def community_homepage():
    logo = '<svg width="90" height="90" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><circle cx="12" cy="11" r="3" stroke="#10b981"/><circle cx="12" cy="11" r="1" fill="#10b981"/></svg>'
    body_content = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>{UPGRADED_CSS} .welcome-title{{font-size:34px; font-weight:900; color:#fff;}}</style></head><body>
        <div class='glass-panel' style='max-width:520px; margin:40px auto; text-align:center;'>
            {logo}<h1 class='welcome-title'>omniwatch.com.ng</h1><span class='badge badge-blue'>[Decentralized Civil Defense Grid]</span>
            <p style='color:var(--text-muted); font-size:14px; margin:15px 0;'>Multiplying neighborhood visibility by linking verified citizens and law enforcement into a single network.</p>
            <div style='display:grid; gap:10px;'><a href='/register' class='btn btn-blue'>[Register]</a><a href='/portal/login' class='btn' style='background:rgba(255,255,255,0.04); color:#fff;'>[Sign In]</a><a href='/dashboard' class='btn' style='background:linear-gradient(135deg,#10b981,#059669); color:white;'>[Open Control Matrix]</a></div>
        </div>{SOCIAL_FOOTER_HTML}</body></html>"""
    return HTMLResponse(content=body_content)

@app.get("/register", response_class=HTMLResponse)
def registration_form():
    body_content = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>{UPGRADED_CSS}</style></head>
    <body><div class='glass-panel' style='max-width:480px; margin:40px auto;'>
        <h2>[Register]</h2><p class='instruction-text'>[Instructions]: Enter your legal name and plain 11-digit phone address starting with 0.</p>
        <form action='/submit-registration' method='post' enctype='multipart/form-data'>
            <label>Full Legal Name</label><input type='text' name='name' required>
            <label>Mobile Phone Number</label><input type='text' name='phone' placeholder='e.g. 08031234567' required>
            <label>Precinct Sector</label><input type='text' name='city_manual' placeholder='e.g. osogbo' required>
            <label>Avatar Profile Picture</label>
            <div style='display:flex; align-items:center; gap:15px; margin:8px 0;'>
                <input type='file' id='picFile' name='profile_pic_file' accept='image/*' onchange='previewAvatar(this)' style='color:var(--text-muted); margin:0;'>
                <img id='picPreview' src='#' style='display:none; width:50px; height:50px; border-radius:50%; object-fit:cover; border:2px solid var(--accent-blue);'>
            </div>
            <label>Primary Music Integration Platform</label>
            <select name='music_provider'>
                <option value=''>None / Skip</option>
                <option value='Spotify'>Spotify</option>
                <option value='Apple Music'>Apple Music</option>
                <option value='Audiomack'>Audiomack</option>
            </select>
            <label>Track or Playlist URL</label><input type='text' name='music_url' placeholder='https://spotify.com...'>
            <br><br><button type='submit' class='btn btn-blue' style='width:100%;'>Complete Registration</button>
        </form>
    </div>
    <script>
    function previewAvatar(input) {{
        const preview = document.getElementById('picPreview');
        if (input.files && input.files[0]) {{
            const reader = new FileReader();
            reader.onload = function(e) {{
                preview.src = e.target.result;
                preview.style.display = 'block';
            }}
            reader.readAsDataURL(input.files[0]);
        }} else {{
            preview.style.display = 'none';
        }}
    }}
    </script>
    {SOCIAL_FOOTER_HTML}</body></html>"""
    return HTMLResponse(content=body_content)

@app.post("/submit-registration")
async def handle_registration(
    name: str = Form(...), phone: str = Form(...), city_manual: str = Form(...),
    music_provider: str = Form(""), music_url: str = Form(""), profile_pic_file: UploadFile = File(None)
):
    clean_p = clean_phone(phone)
    geo = CITY_AUTOFILL_MAP.get(city_manual.lower().strip(), {"country": "Nigeria", "state": "Region", "lga": city_manual, "area": "General Grid"})
    saved_pic_path = ""
    if profile_pic_file and profile_pic_file.filename:
        file_ext = os.path.splitext(profile_pic_file.filename)[1]
        filename = f"{clean_p}{file_ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(profile_pic_file.file, buffer)
        saved_pic_path = f"/static/profile_pics/{filename}"
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("""
            INSERT OR REPLACE INTO citizens (phone, name, country, state, city, lga, area, token, status, xp, profile_pic, music_provider, music_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'token', 'Pending', 100, ?, ?, ?)
        """, (clean_p, sanitize(name), geo["country"], geo["state"], sanitize(city_manual), geo["lga"], geo["area"], saved_pic_path, music_provider, music_url))
        await conn.commit()
    return RedirectResponse(url="/register/success", status_code=303)

@app.get("/register/success", response_class=HTMLResponse)
def register_success_page():
    body_content = f"""<html><head><style>{UPGRADED_CSS}</style></head>
    <body><div class='glass-panel' style='max-width:500px; margin:80px auto; text-align:center;'>
        <div style='font-size:56px; margin-bottom:15px;'>⏳</div>
        <h2>👋 Registration Received Successfully</h2>
        <p style='color:var(--text-muted); line-height:1.6;'>Your defense grid node assignment has been logged into the secure database matrix. Access is restricted until verified by regional command monitors.</p>
        <br><a href='/' class='btn btn-blue' style='width:100%; box-sizing:border-box;'>Return to Home Page Gateway</a>
    </div></body></html>"""
    return HTMLResponse(content=body_content)

@app.get("/portal/login", response_class=HTMLResponse)
def citizen_login_page(error: str = None):
    body_content = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>{UPGRADED_CSS}</style></head>
    <body><div class='glass-panel' style='max-width:400px; margin:80px auto;'>
        <h2>[Sign In]</h2>{f"<p style='color:#ef4444;'>{error}</p>" if error else ""}
        <p class='instruction-text'>[Instructions]: Input your registered phone number to establish your watch session link.</p>
        <form action='/portal/auth' method='post'><label>Phone Number</label><input type='text' name='phone' placeholder='e.g. 08031234567' required><br><br><button type='submit' class='btn btn-blue' style='width:100%;'>Sign In</button></form>
    </div>{SOCIAL_FOOTER_HTML}</body></html>"""
    return HTMLResponse(content=body_content)

@app.post("/portal/auth")
async def citizen_authentication(phone: str = Form(...)):
    target = clean_phone(phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (target,)) as c: citizen = await c.fetchone()
    if citizen:
        if citizen["status"] == "Pending": return HTMLResponse("<h3>Clearance Pending Agency Approval.</h3>")
        res = RedirectResponse(url="/portal/feed", status_code=303)
        res.set_cookie(key="citizen_session", value=sign_cookie_value(target), httponly=True)
        return res
    return RedirectResponse(url="/portal/login?error=Phone number unrecognized.", status_code=303)

@app.get("/portal/citizen/{phone}", response_class=HTMLResponse)
async def view_citizen_profile(phone: str, current_user=Depends(get_current_citizen)):
    target = clean_phone(phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("""
            UPDATE direct_messages SET status = 'Read' 
            WHERE sender = ? AND receiver = ? AND status = 'Active'
        """, (target, current_user['phone']))
        await conn.commit()
        async with conn.execute("SELECT * FROM citizens WHERE phone = ?", (target,)) as c:
            profile = await c.fetchone()
        async with conn.execute("""
            SELECT status FROM trust_network 
            WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
        """, (current_user['phone'], target, target, current_user['phone'])) as tn:
            relationship = await tn.fetchone()
        chat_html = ""
        if relationship and relationship['status'] == 'Approved':
            async with conn.execute("""
                SELECT * FROM direct_messages 
                WHERE ((sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?)) 
                AND status != 'Deleted' 
                ORDER BY timestamp ASC
            """, (current_user['phone'], target, target, current_user['phone'])) as dm:
                messages = await dm.fetchall()
            msg_list = ""
            for m in messages:
                is_me = clean_phone(str(m['sender'])) == clean_phone(str(current_user['phone']))
                align = 'right' if is_me else 'left'
                bg = '#1e3a8a' if is_me else '#1e293b'
                del_btn = f"<form action='/portal/chat/delete' method='post' style='display:inline; margin-left:8px;'><input type='hidden' name='msg_id' value='{m['id']}'><input type='hidden' name='tgt_phone' value='{target}'><button type='submit' style='background:none;border:none;color:#ef4444;cursor:pointer;font-size:10px;'>[Delete]</button></form>"
                msg_list += f"<div style='margin-bottom:8px; text-align:{align};'><span style='background:{bg}; padding:6px 10px; border-radius:8px; display:inline-block; max-width:80%;'>{m['message']} {del_btn}</span></div>"
            chat_badge = " <span class='badge badge-blue' style='padding:2px 6px; font-size:10px;'>📶 Secure Feed Active</span>"
            chat_html = f"""<div class='glass-panel' style='margin-top:20px; padding:15px; border-radius:12px;'><h4>💬 Secure Chat Box{chat_badge}</h4><div style='max-height:180px; overflow-y:auto; background:rgba(0,0,0,0.2); padding:10px; border-radius:8px; margin-bottom:10px;'>{msg_list or '<p style="font-size:12px; color:var(--text-muted); text-align:center;">No active transmissions.</p>'}</div><form action='/portal/chat/send' method='post' style='display:flex; gap:6px; margin:0;'><input type='hidden' name='receiver_phone' value='{target}'><input type='text' name='message' placeholder='Encrypt message...' required style='margin:0;'><button type='submit' class='btn btn-blue' style='padding:0 14px;'>Send</button></form></div>"""

        if not profile: return HTMLResponse(f"<html><head><style>{UPGRADED_CSS}</style></head><body><div class='glass-panel' style='max-width:450px; margin:40px auto; text-align:center;'><h3>❌ Unregistered Terminal</h3><p style='color:var(--text-muted);'>Subscriber number does not exist.</p><br><a href='/portal/feed' class='btn btn-blue'>Return to Feed Stream</a></div></body></html>")
        rel_html = "<p style='color:var(--accent-emerald); font-weight:700;'>🛡️ Linked Trusted Peer</p>" if relationship and relationship['status'] == 'Approved' else f"<form action='/portal/trust/request' method='post'><input type='hidden' name='target_phone' value='{target}'><button type='submit' class='btn btn-blue'>🤝 Send Trust Request</button></form>"
        if relationship and relationship['status'] == 'Pending': rel_html = "<p style='color:var(--badge-amber); font-style:italic;'>⏳ Link Request Pending Approval</p>"
        if relationship and relationship['status'] == 'Rejected': rel_html = "<p style='color:#f87171; font-style:italic;'>🚫 Link Request Declined</p>"
        avatar_src = profile['profile_pic'] if profile['profile_pic'] else ""
        avatar_html = f'<img src="{avatar_src}" style="width:90px; height:90px; border-radius:50%; object-fit:cover; border:2px solid var(--accent-blue); margin-bottom:15px; display:block;">' if avatar_src else '<div style="width:90px; height:90px; border-radius:50%; background:var(--accent-blue); display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:32px; margin-bottom:15px; color:white;">' + profile['name'][:1].upper() + '</div>'
        music_embed_html = generate_music_embed(profile['music_provider'], profile['music_url'])
        body_content = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>{UPGRADED_CSS}</style></head>
        <body><div class='glass-panel' style='max-width:500px; margin:40px auto;'>
            <center>{avatar_html}</center><h2>🛡️ Grid Node Information</h2><hr style='border:1px solid var(--border-glass); margin:15px 0;'>
            <p><b>Legal Identity Name:</b> {profile['name']}</p><p><b>Precinct Sector (City):</b> {profile['city']}</p>
            <p><b>Local Government Area (LGA):</b> {profile['lga']}</p><p><b>Assigned Footprint:</b> {profile['area']}, {profile['state']}</p>
            <p><b>Trust Network Score:</b> <span style='color:var(--accent-emerald); font-weight:bold;'>{profile['xp']} XP</span></p>
            {f"<div style='margin-top:15px;'><b>Connected System Player ({profile['music_provider']}):</b>{music_embed_html}</div>" if music_embed_html else ""}
            <div style='margin-top:20px; text-align:center;'>{rel_html if target != current_user['phone'] else ''}</div>{chat_html}
            <br><a href='/portal/feed' class='btn' style='width:100%; background:rgba(255,255,255,0.05); color:#fff;'>Back to Feed</a>
        </div></body></html>"""
        return HTMLResponse(content=body_content)
@app.get("/portal/chat/send")
def fallback_chat_send_get(): return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/chat/send")
async def send_direct_message(receiver_phone: str = Form(...), message: str = Form(...), current_user=Depends(get_current_citizen)):
    tgt = clean_phone(receiver_phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
                "SELECT status FROM trust_network WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)",
                (current_user['phone'], tgt, tgt, current_user['phone'])) as tn:
            relationship = await tn.fetchone()
        if not relationship or relationship['status'] != 'Approved': raise HTTPException(status_code=403, detail="Not trusted peers")
        await conn.execute("INSERT INTO direct_messages (sender, receiver, message, status) VALUES (?, ?, ?, 'Active')", (current_user['phone'], tgt, sanitize(message)))
        await conn.commit()
    return RedirectResponse(url=f"/portal/citizen/{tgt}", status_code=303)

@app.post("/portal/chat/delete")
async def delete_direct_message(msg_id: int = Form(...), tgt_phone: str = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE direct_messages SET status = 'Deleted' WHERE id = ? AND (sender = ? OR receiver = ?)", (msg_id, current_user['phone'], current_user['phone']))
        await conn.commit()
    return RedirectResponse(url=f"/portal/citizen/{clean_phone(tgt_phone)}", status_code=303)

@app.post("/portal/viral/post")
async def post_viral_broadcast(context: str = Form(...), visibility: str = Form("Public"),
                               current_user=Depends(get_current_citizen)):
    if len(context.strip()) > 250: raise HTTPException(status_code=400, detail="Transmission exceeds maximum threshold")
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("""
            INSERT INTO viral_posts (author, phone, context, status, visibility) 
            VALUES (?, ?, ?, 'Pending', ?)
        """, (current_user['name'], current_user['phone'], sanitize(context), visibility))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.get("/portal/feed", response_class=HTMLResponse)
async def user_portal_feed(current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("""
            SELECT name, phone, profile_pic, music_provider, music_url FROM citizens WHERE phone IN (
                SELECT sender FROM trust_network WHERE receiver = ? AND status = 'Approved' UNION SELECT receiver FROM trust_network WHERE sender = ? AND status = 'Approved'
            )
        """, (current_user['phone'], current_user['phone'])) as cx: neighbors = await cx.fetchall()
        trusted_phones = [clean_phone(str(n['phone'])) for n in neighbors]

        async with conn.execute("SELECT sender FROM direct_messages WHERE receiver = ? AND status = 'Active'",
                                (current_user['phone'],)) as dm_check:
            unread_rows = await dm_check.fetchall()
            senders_with_messages = {clean_phone(str(r['sender'])) for r in unread_rows}
        neighbors_html = ""
        for n in neighbors:
            avatar_block = f'<img src="{n["profile_pic"]}" style="width:36px; height:36px; border-radius:50%; object-fit:cover;">' if n['profile_pic'] else f"<div style='width:36px; height:36px; border-radius:50%; background:#3b82f6; display:flex; align-items:center; justify-content:center; font-weight:bold; color:#fff;'>{n['name'][:1].upper()}</div>"
            envelope_sign = ""
            if clean_phone(str(n['phone'])) in senders_with_messages:
                envelope_sign = '<span class="retro-envelope" title="New Message"></span>'
            neighbors_html += f"""<div class='neighbor-item' data-search='{n['name'].lower()} {n['phone']}' style='display:flex; align-items:center; gap:12px; padding:10px; background:rgba(255,255,255,0.02); border-radius:10px; margin-bottom:8px;'>{avatar_block}<div style='flex-grow:1;'><div style='font-size:14px; font-weight:700; display:flex; align-items:center; gap:8px;'><a href='/portal/citizen/{n['phone']}' style='color:#60a5fa; text-decoration:none;'>{n['name']}</a>{envelope_sign}</div><div style='font-size:11px; color:var(--text-muted);'>🛡️ Linked Peer</div></div></div>"""

        async with conn.execute("SELECT * FROM viral_posts WHERE status != 'Deleted' AND (status = 'Approved' OR phone = ?) ORDER BY id DESC", (current_user['phone'],)) as c: posts = await c.fetchall()
        feed_html = ""
        for p in posts:
            is_owner = clean_phone(str(p['phone'])) == clean_phone(str(current_user['phone']))
            if not is_owner:
                if p['visibility'] == 'Private': continue
                if not (p['status'] in ('Approved', 'Reported') and clean_phone(str(p['phone'])) in trusted_phones): continue
            async with conn.execute("SELECT profile_pic, music_provider, music_url FROM citizens WHERE phone = ?", (p['phone'],)) as auth_info: author_meta = await auth_info.fetchone()
            p_avatar = f'<img src="{author_meta["profile_pic"]}" style="width:28px; height:28px; border-radius:50%; object-fit:cover; vertical-align:middle; margin-right:6px;">' if author_meta and author_meta['profile_pic'] else ""
            p_music_embed = generate_music_embed(author_meta['music_provider'], author_meta['music_url']) if author_meta else ""
            async with conn.execute("SELECT * FROM viral_comments WHERE post_id = ? AND status != 'Deleted' ORDER BY id ASC", (p['id'],)) as cc: comments = await cc.fetchall()
            cm_html = ""
            for cmt in comments:
                rep_btn = f"<form action='/portal/viral/comment/report' method='post' style='display:inline; margin-left:6px;'><input type='hidden' name='comment_id' value='{cmt['id']}'><button type='submit' style='background:none; border:none; color:#f87171; opacity:0.6; cursor:pointer; font-size:11px; padding:0;'>⚠️</button></form>" if cmt['phone'] != current_user['phone'] else ""
                cmt_link = f"/portal/citizen/{cmt['phone']}" if cmt['phone'] else "#"
                cm_html += f"<div class='comment-box'><b><a href='{cmt_link}' style='color:#60a5fa; text-decoration:none;'>{cmt['author']}</a>:</b> {cmt['text']} {rep_btn}</div>"
            badge = "<span class='badge badge-blue'>🟢 Verified Broadcast</span>"
            if p['status'] == 'Pending':
                badge = "<span class='badge badge-amber'>⏳ Awaiting Verification</span>"
            elif p['status'] == 'Reported':
                badge = "<span class='badge' style='background:rgba(239,68,68,0.15); color:#f87171;'>⚠️ Flagged</span>"
            vis_badge = f" <span class='badge' style='background:rgba(255,255,255,0.1); color:#fff;'>👁️ {p['visibility']}</span>"
            mgmt_actions = ""
            if is_owner:
                next_vis = "Private" if p['visibility'] == "Public" else "Public"
                mgmt_actions = f"""<div style='margin-top:10px; display:flex; gap:10px;'><form action='/portal/viral/post/toggle-visibility' method='post' style='margin:0;'><input type='hidden' name='post_id' value='{p['id']}'><input type='hidden' name='visibility' value='{next_vis}'><button type='submit' class='btn' style='padding:4px 10px; font-size:12px; background:#475569; color:#fff;'>Make {next_vis}</button></form><form action='/portal/viral/post/delete' method='post' style='margin:0;'><input type='hidden' name='post_id' value='{p['id']}'><button type='submit' class='btn' style='padding:4px 10px; font-size:12px; background:#ef4444; color:#fff;'>Delete Update</button></form></div>"""
            rep_p_btn = f"<form action='/portal/viral/post/report' method='post' style='display:inline-block; margin-left:8px;'><input type='hidden' name='post_id' value='{p['id']}'><button type='submit' title='Report broadcast' style='background:none; border:none; color:#f87171; opacity:0.6; cursor:pointer; font-size:12px; padding:0;'>⚠️</button></form>" if \
            p['phone'] != current_user['phone'] and p['status'] != 'Reported' else ""
            feed_html += f"""<div class='glass-panel' style='margin-bottom:16px; padding:20px;'><h4>{p_avatar}📣 <a href='/portal/citizen/{p['phone']}' style='color:#fff; text-decoration:none;'>{p['author']}</a> {badge}{vis_badge} {rep_p_btn}</h4><p>"{p['context']}"</p>{f'<div style="margin:8px 0;">{p_music_embed}</div>' if p_music_embed else ''}{mgmt_actions}<div style='margin-top:12px; border-top:1px solid var(--border-glass); padding-top:10px;'>{cm_html or '<p style="font-size:12px; color:var(--text-muted); font-style:italic;">No comments yet.</p>'}<form action='/portal/viral/comment' method='post' style='margin-top:8px; display:flex; gap:6px;'><input type='hidden' name='post_id' value='{p['id']}'><input type='text' name='text' placeholder='Reply...' required style='margin:0;'><button type='submit' class='btn btn-blue' style='padding:4px 12px; font-size:12px;'>Reply</button></form></div></div>"""
        async with conn.execute(
            "SELECT t.id, c.name, t.sender FROM trust_network t JOIN citizens c ON t.sender = c.phone WHERE t.receiver = ? AND t.status = 'Pending'",
            (current_user['phone'],)) as tx:
            incoming_reqs = await tx.fetchall()
        async with conn.execute(
            "SELECT t.id, c.name, t.receiver FROM trust_network t JOIN citizens c ON t.receiver = c.phone WHERE t.sender = ? AND t.status = 'Pending'",
            (current_user['phone'],)) as ty:
            outgoing_reqs = await ty.fetchall()

        req_html = ""
        for r in incoming_reqs:
            req_html += f"""<div style='display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:5px; background:rgba(255,255,255,0.01); padding:5px; border-radius:6px;'>
                <span style='font-size:13px;'>{r['name']}</span>
                <div style='display:flex; gap:4px;'>
                    <form action='/portal/trust/accept' method='post' style='margin:0;'><input type='hidden' name='request_id' value='{r['id']}'><button type='submit' class='btn btn-blue' style='padding:4px 8px; font-size:11px;'>Accept</button></form>
                    <form action='/portal/trust/reject' method='post' style='margin:0;'><input type='hidden' name='request_id' value='{r['id']}'><button type='submit' class='btn' style='padding:4px 8px; font-size:11px; background:#ef4444; color:#fff;'>Reject</button></form>
                </div>
            </div>"""

        sent_html = ""
        for r in outgoing_reqs:
            sent_html += f"<div style='font-size:13px; color:var(--text-muted); margin-bottom:4px;'>⏳ Request sent to {r['name']}</div>"

    live_scripts = """
    <script>
    function filterNeighbors(val) {
        let text = val.toLowerCase().trim();
        document.querySelectorAll('.neighbor-item').forEach(item => {
            let searchSpace = item.getAttribute('data-search');
            if (searchSpace.includes(text)) {
                item.style.setProperty('display', 'flex', 'important');
            } else {
                item.style.setProperty('display', 'none', 'important');
            }
        });
    }
    function updateCounter(textarea) {
        const count = textarea.value.length;
        const display = document.getElementById('charCount');
        display.innerText = count + ' / 250';
        if (count > 250) {
            display.style.color = '#ef4444';
        } else {
            display.style.color = 'var(--text-muted)';
        }
    }
    </script>
    """
    body_content = f"""<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>{UPGRADED_CSS}</style>{live_scripts}</head><body><div class='container' style='max-width:900px; margin:0 auto; display:grid; grid-template-columns: 2fr 1fr; gap:20px;'><div><div class='glass-panel' style='margin-bottom:20px;'>Override Security Terminal Mode Link Core Grid Matrix Gateway.<h3>👋 Welcome, <a href='/portal/citizen/{current_user['phone']}' style='color:var(--accent-blue); text-decoration:underline;'>{current_user['name']}</a></h3><p class='instruction-text'>💡 <b>Instructions:</b> Share an update. It will remain private until approved by regional monitors.</p><form action='/portal/viral/post' method='post'><textarea name='context' maxlength='250' oninput='updateCounter(this)' style='width:100%; height:60px; background:#090d16; color:#fff; margin-bottom:2px;' placeholder='What is happening...' required></textarea><div id='charCount' style='text-align:right; font-size:11px; color:var(--text-muted); margin-bottom:10px;'>0 / 250</div><label>Broadcast Visibility Type</label><select name='visibility' style='margin-top:5px;'><option value='Public'>Public (Trusted Peers Can View)</option><option value='Private'>Private (Only You Can View)</option></select><br><button type='submit' class='btn btn-blue' style='width:100%; margin-top:5px;'>Submit Broadcast</button></form></div><h3>📡 Broadcast Stream Feed</h3>{feed_html or '<p style="color:var(--text-muted); font-style:italic;">No dispatches available.</p>'}</div><div><div class='glass-panel' style='margin-bottom:20px;'><h3>👥 Trusted Neighbors ({len(neighbors)})</h3><input type='text' id='neighborSearch' placeholder='🔍 Search peers name or phone...' onkeyup='filterNeighbors(this.value)' style='margin-bottom:12px; padding:8px 12px; font-size:13px;'><div id='neighborsContainer' style='max-height:220px; overflow-y:auto;'>{neighbors_html or '<p style="color:var(--text-muted); font-size:12px; font-style:italic;">No connected peers.</p>'}</div></div><div class='glass-panel' style='margin-bottom:20px;'><h3>🤝 Trust Network Gate</h3><form action='/portal/trust/lookup' method='post' style='display:flex; gap:8px;'><input type='text' name='target_phone' placeholder='Lookup 11-digit mobile...' required style='margin:0;'><button type='submit' class='btn btn-blue' style='padding:0 12px;'>Search</button></form><div style='margin-top:15px;'><h5>📥 Incoming Requests</h5>{req_html or '<p style=\"color:var(--text-muted); font-size:12px;\">No pending actions.</p>'}</div><div style='margin-top:15px;'><h5>📤 Sent Outgoing Log</h5>{sent_html or '<p style=\"color:var(--text-muted); font-size:12px;\">No active pending links.</p>'}</div></div><center><a href='/portal/logout' class='btn' style='background:rgba(239,68,68,0.15); color:#f87171; width:100%;'>Disconnect Terminal</a></center></div></div></body></html>"""
    return HTMLResponse(content=body_content)
@app.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    async with aiosqlite.connect(DB_FILE) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM citizens WHERE status != 'Deleted'") as c1: all_users = await c1.fetchall()
        async with conn.execute("SELECT * FROM viral_posts WHERE status IN ('Pending', 'Reported')") as c2: pending_posts = await c2.fetchall()
        async with conn.execute("SELECT * FROM viral_comments WHERE status = 'Reported'") as c3: reported_comments = await c3.fetchall()
        async with conn.execute("SELECT * FROM direct_messages WHERE status = 'Active' ORDER BY id DESC") as c4: active_dms = await c4.fetchall()
    u_rows = "".join([f"<tr><td>{u['name']}</td><td>0{u['phone']}</td><td><b>{u['status']}</b></td><td>" + (f"<form action='/admin/approve-citizen' method='post'><input type='hidden' name='phone' value='{u['phone']}'><button type='submit' class='btn btn-blue' style='padding:6px 12px;'>Approve</button></form>" if u['status'] == 'Pending' else "") + f"<form action='/admin/delete-citizen' method='post' style='display:inline; margin-left:5px;'><input type='hidden' name='phone' value='{u['phone']}'><button type='submit' class='btn' style='background:#ef4444; color:#fff; padding:6px 12px;'>Purge User</button></form></td></tr>" for u in all_users])
    p_rows = ""
    for p in pending_posts:
        lbl = "⚠️ Reported" if p['status'] == 'Reported' else "⏳ New"
        p_rows += f"<tr><td><span class='badge' style='background:rgba(239,68,68,0.2); margin-right:5px;'>{lbl}</span> <b>{p['author']}:</b> {p['context']} ({p['visibility']})</td><td><div style='display:flex; gap:5px;'><form action='/admin/approve-post' method='post'><input type='hidden' name='id' value='{p['id']}'><button type='submit' class='btn btn-blue' style='padding:6px 12px; background:#10b981;'>Approve</button></form><form action='/admin/delete-post' method='post'><input type='hidden' name='id' value='{p['id']}'><button type='submit' class='btn' style='background:#ef4444; color:#fff; padding:6px 12px;'>Delete</button></form></div></td></tr>"
    c_rows = "".join([f"""<tr><td><b>{c['author']}:</b> {c['text']}</td><td><div style='display:flex; gap:5px;'><form action='/admin/approve-comment' method='post'><input type='hidden' name='id' value='{c['id']}'><button type='submit' class='btn btn-blue' style='padding:6px 12px; background:#10b981;'>Dismiss</button></form><form action='/admin/delete-comment' method='post'><input type='hidden' name='id' value='{c['id']}'><button type='submit' class='btn' style='background:#ef4444; color:#fff; padding:6px 12px;'>Delete</button></form></div></td></tr>""" for c in reported_comments])
    m_rows = "".join([f"""<tr><td><b>From:</b> 0{m['sender']} | <b>To:</b> 0{m['receiver']} <br><span style='color:var(--text-muted);'>"{m['message']}"</span></td><td><form action='/admin/delete-message' method='post'><input type='hidden' name='id' value='{m['id']}'><button type='submit' class='btn' style='background:#ef4444; color:#fff; padding:6px 12px;'>Delete Msg</button></form></td></tr>""" for m in active_dms])
    body_content = f"""<html><head><style>{UPGRADED_CSS} th, td {{padding:12px; border-bottom:1px solid var(--border-glass); text-align:left; color:#fff;}}</style></head><body><div class='container' style='max-width:850px; margin:0 auto; padding-top:20px;'><h2>🛡️ Regional Control Panel Matrix</h2><div class='glass-panel' style='margin-bottom:20px;'><h3>👥 Registered System Citizens</h3><table style='width:100%; border-collapse:collapse;'>{u_rows or '<tr><td>No records found.</td></tr>'}</table></div><div class='glass-panel' style='margin-bottom:20px;'><h3>📣 Broadcast Content Moderation Matrix</h3><table style='width:100%; border-collapse:collapse;'>{p_rows or '<tr><td>No posts awaiting action.</td></tr>'}</table></div><div class='glass-panel' style='margin-bottom:20px;'><h3>💬 Reported Community Comments</h3><table style='width:100%; border-collapse:collapse;'>{c_rows or '<tr><td>No reported comments.</td></tr>'}</table></div><div class='glass-panel'><h3>📥 Live Chat Monitor Wire Desk (Pass-Through)</h3><table style='width:100%; border-collapse:collapse;'>{m_rows or '<tr><td>No active transmissions logged.</td></tr>'}</table></div><br><center><a href='/' class='btn' style='background:rgba(255,255,255,0.05); color:#cbd5e1;'>Return to Home Page</a></center></div></body></html>"""
    return HTMLResponse(content=body_content)

@app.post("/admin/approve-citizen")
async def app_cit(phone: str = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE citizens SET status = 'Approved' WHERE phone = ?", (phone,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin/delete-citizen")
async def del_cit(phone: str = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE citizens SET status = 'Deleted' WHERE phone = ?", (phone,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)
@app.post("/admin/approve-post")
async def app_pos(id: int = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE viral_posts SET status = 'Approved' WHERE id = ?", (id,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin/delete-post")
async def del_pos(id: int = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE viral_posts SET status = 'Deleted' WHERE id = ?", (id,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin/approve-comment")
async def app_cmt(id: int = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE viral_comments SET status = 'Approved' WHERE id = ?", (id,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin/delete-comment")
async def del_cmt(id: int = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE viral_comments SET status = 'Deleted' WHERE id = ?", (id,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin/delete-message")
async def del_msg(id: int = Form(...)):
    async with aiosqlite.connect(DB_FILE) as conn: await conn.execute("UPDATE direct_messages SET status = 'Deleted' WHERE id = ?", (id,)); await conn.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/portal/viral/post/toggle-visibility")
async def toggle_post_visibility(post_id: int = Form(...), visibility: str = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET visibility = ? WHERE id = ? AND phone = ?", (visibility, post_id, current_user['phone']))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/viral/post/delete")
async def delete_post(post_id: int = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET status = 'Deleted' WHERE id = ? AND phone = ?", (post_id, current_user['phone']))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/viral/post/report")
async def report_post(post_id: int = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_posts SET status = 'Reported' WHERE id = ?", (post_id,))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.get("/portal/logout")
def handle_logout():
    r = RedirectResponse(url="/", status_code=303); r.delete_cookie("citizen_session"); return r

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=4444, reload=True)

@app.post("/portal/viral/comment")
async def comment_viral_post(post_id: int = Form(...), text: str = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("INSERT INTO viral_comments (post_id, author, phone, text, status) VALUES (?, ?, ?, ?, 'Approved')", (post_id, current_user['name'], current_user['phone'], sanitize(text)))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/viral/comment/report")
async def report_viral_comment(comment_id: int = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE viral_comments SET status = 'Reported' WHERE id = ?", (comment_id,))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/trust/lookup")
async def trust_profile_lookup(target_phone: str = Form(...), current_user=Depends(get_current_citizen)):
    return RedirectResponse(url=f"/portal/citizen/{clean_phone(target_phone)}", status_code=303)

@app.post("/portal/trust/request")
async def send_trust_request(target_phone: str = Form(...), current_user=Depends(get_current_citizen)):
    target = clean_phone(target_phone)
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("INSERT OR REPLACE INTO trust_network (sender, receiver, status) VALUES (?, ?, 'Pending')", (current_user['phone'], target))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/trust/accept")
async def accept_trust_request(request_id: int = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE trust_network SET status = 'Approved' WHERE id = ? AND receiver = ?", (request_id, current_user['phone']))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)

@app.post("/portal/trust/reject")
async def reject_trust_request(request_id: int = Form(...), current_user=Depends(get_current_citizen)):
    async with aiosqlite.connect(DB_FILE) as conn:
        await conn.execute("UPDATE trust_network SET status = 'Rejected' WHERE id = ? AND receiver = ?", (request_id, current_user['phone']))
        await conn.commit()
    return RedirectResponse(url="/portal/feed", status_code=303)
