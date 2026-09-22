#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ترباس — سيرفر كامل"""
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, sqlite3, re, mimetypes, os
from datetime import datetime

HOST, PORT = "0.0.0.0", int(os.environ.get("PORT", 5000))
ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
if not (STATIC / "index.html").exists():
    STATIC = ROOT
DB = ROOT / "data" / "turbas.db"
DB.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE, name TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, brand TEXT, model TEXT, generation TEXT, year TEXT, color TEXT
    );
    CREATE TABLE IF NOT EXISTS partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, type TEXT DEFAULT 'workshop', area TEXT DEFAULT 'صناعية العاصمة'
    );
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, name TEXT, problem TEXT, price REAL,
        duration TEXT, warranty_days INTEGER, description TEXT,
        brands TEXT DEFAULT '', models TEXT DEFAULT '',
        parts_changed TEXT DEFAULT '', includes TEXT DEFAULT '',
        labor_only INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, name TEXT, category TEXT, price REAL,
        meta TEXT, warranty TEXT,
        part_number TEXT DEFAULT '', origin TEXT DEFAULT '',
        grade TEXT DEFAULT 'تجاري',
        brands TEXT DEFAULT '', models TEXT DEFAULT '',
        years TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, partner_id INTEGER, title TEXT, type TEXT,
        price REAL, delivery_fee REAL DEFAULT 0,
        status TEXT DEFAULT 'new', status_text TEXT DEFAULT 'قيد المراجعة',
        car_info TEXT, zone TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, sender TEXT, body TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, points INTEGER, label TEXT, created_at TEXT
    );
    """)
    # migrate columns if old DB
    for table, col, typ in [
        ("services", "brands", "TEXT DEFAULT ''"),
        ("services", "models", "TEXT DEFAULT ''"),
        ("services", "parts_changed", "TEXT DEFAULT ''"),
        ("services", "includes", "TEXT DEFAULT ''"),
        ("services", "labor_only", "INTEGER DEFAULT 1"),
        ("parts", "part_number", "TEXT DEFAULT ''"),
        ("parts", "origin", "TEXT DEFAULT ''"),
        ("parts", "grade", "TEXT DEFAULT 'تجاري'"),
        ("parts", "brands", "TEXT DEFAULT ''"),
        ("parts", "models", "TEXT DEFAULT ''"),
        ("parts", "years", "TEXT DEFAULT ''"),
    ]:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        except Exception:
            pass

    if c.execute("SELECT COUNT(*) FROM partners").fetchone()[0] == 0:
        partners = [
            ("ورشة رقم 1", "0500000001", "workshop", "صناعية العاصمة"),
            ("ورشة رقم 2", "0500000002", "workshop", "صناعية العاصمة"),
            ("ورشة رقم 3", "0500000003", "workshop", "صناعية العاصمة"),
            ("محل رقم 6", "0500000006", "parts", "صناعية العاصمة"),
            ("محل رقم 8", "0500000008", "parts", "صناعية العاصمة"),
        ]
        c.executemany("INSERT INTO partners (name, phone, type, area) VALUES (?,?,?,?)", partners)
        services = [
            (1, "تغيير زيت مكينة", "صيانة دورية", 220, "45 دقيقة", 30, "خدمة يد عاملة — الزيت حسب اختيارك",
             "تويوتا,لكزس", "كامري,كورولا,ES", "فلتر زيت", "فك وتركيب فلتر · تصفية الزيت · فحص مستوى", 1),
            (1, "إصلاح رديتر", "رديتر وتبريد", 350, "ساعتين", 60, "فحص ولحام أو تبديل",
             "تويوتا,نيسان", "لاندكروزر,باترول Y62", "رديتر / غطاء", "فحص ضغط · لحام أو تبديل · تعبئة", 0),
            (2, "تغيير فحمات أمامية", "فرامل", 280, "ساعة ونص", 60, "فحمات سيراميك",
             "هيونداي,كيا", "النترا,سيراتو", "فحمات أمامية", "فك وتركيب · تنظيف دسكات", 0),
            (3, "فحص كمبيوتر", "كهرباء", 120, "30 دقيقة", 7, "قراءة أكواد وتقرير",
             "", "", "", "تقرير أكواد", 1),
        ]
        c.executemany("""INSERT INTO services
            (partner_id,name,problem,price,duration,warranty_days,description,brands,models,parts_changed,includes,labor_only)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", services)
        parts = [
            (4, "شل هيلكس 5W-30", "زيوت", 85, "4 لتر", "ضمان المحل", "SHX530", "هولندا", "درجة أولى", "تويوتا,هيونداي", "كامري,النترا", "2015-2024"),
            (4, "أكوم 70 أمبير", "بطاريات", 380, "70A", "18 شهر", "AC70", "السعودية", "تجاري", "تويوتا,نيسان", "كامري,التيما", "2012-2024"),
            (5, "بوش S5 90 أمبير", "بطاريات", 720, "90A", "36 شهر", "BOSCHS590", "ألمانيا", "أصلي", "شيفروليه,جمس", "تاهو,يوكون", "2015-2024"),
            (5, "فلتر زيت تويوتا أصلي", "فلاتر", 45, "OEM", "ضمان المحل", "90915-YZZD2", "اليابان", "أصلي", "تويوتا", "كامري,كورولا", "2018-2024"),
        ]
        c.executemany("""INSERT INTO parts
            (partner_id,name,category,price,meta,warranty,part_number,origin,grade,brands,models,years)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", parts)
        c.execute("INSERT INTO users (phone, name, created_at) VALUES (?,?,?)",
                  ("0512345678", "عميل تجريبي", datetime.now().isoformat()))
        uid = c.lastrowid
        c.execute("INSERT INTO cars (user_id,brand,model,generation,year,color) VALUES (?,?,?,?,?,?)",
                  (uid, "تويوتا", "كامري", "2018-2024 (XV70)", "2021", "أبيض"))
        c.execute("""INSERT INTO orders (user_id,partner_id,title,type,price,delivery_fee,status,status_text,car_info,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (uid, 1, "تغيير زيت مكينة", "service", 280, 0, "active", "جاري التنفيذ", "كامري 2021", datetime.now().isoformat()))
        c.execute("INSERT INTO points_log (user_id,points,label,created_at) VALUES (?,?,?,?)",
                  (uid, 28, "طلب تجريبي", datetime.now().isoformat()))
    c.execute("UPDATE partners SET area=?", ("صناعية العاصمة",))
    conn.commit()
    conn.close()

def j(rows):
    return [dict(r) for r in rows]

class App(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STATIC), **k)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS,DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n: return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path, qs = u.path, parse_qs(u.query)

        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if path in ("/partner", "/partner.html"):
            return self._file(STATIC / "partner.html")

        if path == "/api/health":
            return self._send_json(200, {"ok": True, "service": "turbas"})

        if path == "/api/delivery-zones":
            return self._send_json(200, [
                {"id": "sinaeya", "name": "صناعية العاصمة", "fee": 15},
                {"id": "nearby", "name": "أحياء قريبة من الصناعية", "fee": 25},
                {"id": "riyadh", "name": "باقي الرياض", "fee": 35},
            ])

        if path == "/api/partners":
            conn = get_db()
            data = j(conn.execute("SELECT id,name,phone,type,area FROM partners").fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/services":
            conn = get_db()
            q = """SELECT s.*, p.name as partner_name, p.area as partner_area FROM services s
                   JOIN partners p ON p.id=s.partner_id WHERE 1=1"""
            params = []
            if "partner_id" in qs:
                q += " AND s.partner_id=?"; params.append(qs["partner_id"][0])
            if "problem" in qs and qs["problem"][0] != "الكل":
                q += " AND s.problem=?"; params.append(qs["problem"][0])
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/parts":
            conn = get_db()
            q = """SELECT pt.*, p.name as partner_name, p.area as partner_area FROM parts pt
                   JOIN partners p ON p.id=pt.partner_id WHERE 1=1"""
            params = []
            if "partner_id" in qs:
                q += " AND pt.partner_id=?"; params.append(qs["partner_id"][0])
            if "category" in qs and qs["category"][0] != "الكل":
                q += " AND pt.category=?"; params.append(qs["category"][0])
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/orders":
            conn = get_db()
            q = """SELECT o.*, p.name as partner_name FROM orders o
                   LEFT JOIN partners p ON p.id=o.partner_id WHERE 1=1"""
            params = []
            if "user_id" in qs:
                q += " AND o.user_id=?"; params.append(qs["user_id"][0])
            if "partner_id" in qs:
                q += " AND o.partner_id=?"; params.append(qs["partner_id"][0])
            if "status" in qs:
                q += " AND o.status=?"; params.append(qs["status"][0])
            q += " ORDER BY o.id DESC"
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/users/(\d+)/cars$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM cars WHERE user_id=?", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/users/(\d+)/points$", path)
        if m:
            conn = get_db()
            uid = m.group(1)
            log = j(conn.execute("SELECT * FROM points_log WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall())
            total = conn.execute("SELECT COALESCE(SUM(points),0) FROM points_log WHERE user_id=?", (uid,)).fetchone()[0]
            conn.close()
            return self._send_json(200, {"total": total, "log": log})

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM messages WHERE order_id=? ORDER BY id ASC", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/orders/(\d+)$", path)
        if m:
            conn = get_db()
            row = conn.execute("SELECT o.*, p.name as partner_name FROM orders o LEFT JOIN partners p ON p.id=o.partner_id WHERE o.id=?", (m.group(1),)).fetchone()
            conn.close()
            if not row: return self._send_json(404, {"error": "not found"})
            return self._send_json(200, dict(row))

        f = STATIC / path.lstrip("/")
        if f.is_file():
            return self._file(f)
        return self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()

        if path == "/api/auth/login":
            phone = (data.get("phone") or "").strip()
            if not phone: return self._send_json(400, {"error": "رقم الجوال مطلوب"})
            conn = get_db()
            row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (phone,name,created_at) VALUES (?,?,?)",
                             (phone, data.get("name") or "عميل", datetime.now().isoformat()))
                conn.commit()
                row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            user = dict(row)
            conn.close()
            return self._send_json(200, {"user": user})

        if path == "/api/partners/login":
            phone = (data.get("phone") or "").strip()
            conn = get_db()
            row = conn.execute("SELECT * FROM partners WHERE phone=?", (phone,)).fetchone()
            conn.close()
            if not row: return self._send_json(404, {"error": "غير مسجل — جرب 0500000001"})
            return self._send_json(200, {"partner": dict(row)})

        if path == "/api/services":
            conn = get_db()
            conn.execute("""INSERT INTO services
                (partner_id,name,problem,price,duration,warranty_days,description,brands,models,parts_changed,includes,labor_only)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (data.get("partner_id"), data.get("name"), data.get("problem") or "صيانة دورية",
                 data.get("price", 0), data.get("duration") or "", data.get("warranty_days", 30),
                 data.get("description") or "", data.get("brands") or "", data.get("models") or "",
                 data.get("parts_changed") or "", data.get("includes") or "",
                 1 if data.get("labor_only", True) else 0))
            conn.commit()
            sid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": sid, "ok": True})

        if path == "/api/parts":
            conn = get_db()
            conn.execute("""INSERT INTO parts
                (partner_id,name,category,price,meta,warranty,part_number,origin,grade,brands,models,years)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (data.get("partner_id"), data.get("name"), data.get("category") or "فلاتر",
                 data.get("price", 0), data.get("meta") or "", data.get("warranty") or "ضمان المحل",
                 data.get("part_number") or "", data.get("origin") or "",
                 data.get("grade") or "تجاري", data.get("brands") or "",
                 data.get("models") or "", data.get("years") or ""))
            conn.commit()
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": pid, "ok": True})

        if path == "/api/orders":
            conn = get_db()
            conn.execute("""INSERT INTO orders
                (user_id,partner_id,title,type,price,delivery_fee,status,status_text,car_info,zone,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (data.get("user_id"), data.get("partner_id"), data.get("title"), data.get("type","service"),
                 data.get("price",0), data.get("delivery_fee",0), "new", "قيد المراجعة",
                 data.get("car_info"), data.get("zone"), datetime.now().isoformat()))
            conn.commit()
            oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            pts = int((data.get("price") or 0) // 10)
            if pts and data.get("user_id"):
                conn.execute("INSERT INTO points_log (user_id,points,label,created_at) VALUES (?,?,?,?)",
                             (data["user_id"], pts, "طلب #%s" % oid, datetime.now().isoformat()))
                conn.commit()
            conn.close()
            return self._send_json(201, {"id": oid, "points_earned": pts})

        m = re.match(r"^/api/orders/(\d+)/status$", path)
        if m:
            oid = m.group(1)
            status_text = data.get("status_text") or data.get("status") or "محدث"
            status = "active"
            if status_text in ("جاهز / مكتمل", "مكتمل"): status = "done"
            elif status_text in ("قيد المراجعة",): status = "new"
            conn = get_db()
            conn.execute("UPDATE orders SET status=?, status_text=? WHERE id=?", (status, status_text, oid))
            conn.commit()
            conn.close()
            return self._send_json(200, {"ok": True, "status": status, "status_text": status_text})

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            oid = m.group(1)
            conn = get_db()
            conn.execute("INSERT INTO messages (order_id,sender,body,created_at) VALUES (?,?,?,?)",
                         (oid, data.get("sender","customer"), data.get("body",""), datetime.now().isoformat()))
            conn.commit()
            mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": mid})

        return self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/services/(\d+)$", path)
        if m:
            conn = get_db()
            conn.execute("DELETE FROM services WHERE id=?", (m.group(1),))
            conn.commit(); conn.close()
            return self._send_json(200, {"ok": True})
        m = re.match(r"^/api/parts/(\d+)$", path)
        if m:
            conn = get_db()
            conn.execute("DELETE FROM parts WHERE id=?", (m.group(1),))
            conn.commit(); conn.close()
            return self._send_json(200, {"ok": True})
        return self._send_json(404, {"error": "not found"})

    def _file(self, path: Path):
        if not path.is_file():
            return self._send_json(404, {"error": "file not found"})
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

if __name__ == "__main__":
    init_db()
    print("ترباس → http://127.0.0.1:%d" % PORT)
    HTTPServer((HOST, PORT), App).serve_forever()
