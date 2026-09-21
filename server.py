#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ترباس — سيرفر كامل (موقع العميل + لوحة الورش + API)
===============================================
تشغيل:
  cd turbas
  python3 server.py

ثم افتح:
  http://127.0.0.1:5000          ← موقع العميل
  http://127.0.0.1:5000/partner  ← لوحة الورش
  http://127.0.0.1:5000/api/health
"""
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import json, sqlite3, re, mimetypes
from datetime import datetime

import os
HOST, PORT = "0.0.0.0", int(os.environ.get("PORT", 5000))
ROOT = Path(__file__).resolve().parent
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
        name TEXT, phone TEXT UNIQUE, type TEXT DEFAULT 'workshop', area TEXT DEFAULT 'الرياض'
    );
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, name TEXT, problem TEXT, price REAL,
        duration TEXT, warranty_days INTEGER, description TEXT
    );
    CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, name TEXT, category TEXT, price REAL,
        meta TEXT, warranty TEXT
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
    if c.execute("SELECT COUNT(*) FROM partners").fetchone()[0] == 0:
        partners = [
            ("ورشة رقم 1", "0500000001", "workshop", "شمال الرياض"),
            ("ورشة رقم 2", "0500000002", "workshop", "وسط الرياض"),
            ("ورشة رقم 3", "0500000003", "workshop", "شرق الرياض"),
            ("محل رقم 6", "0500000006", "parts", "وسط الرياض"),
            ("محل رقم 8", "0500000008", "parts", "جنوب الرياض"),
        ]
        c.executemany("INSERT INTO partners (name, phone, type, area) VALUES (?,?,?,?)", partners)
        services = [
            (1, "تغيير زيت مكينة", "صيانة دورية", 220, "45 دقيقة", 30, "زيت + فلتر"),
            (1, "إصلاح رديتر", "رديتر وتبريد", 350, "ساعتين", 60, "فحص ولحام أو تبديل"),
            (1, "صيانة دورية كاملة", "صيانة دورية", 450, "ساعتين", 30, "زيت + فلاتر + فحص"),
            (2, "تغيير فحمات أمامية", "فرامل", 280, "ساعة ونص", 60, "فحمات سيراميك"),
            (2, "صيانة قير", "قير", 450, "3 ساعات", 90, "زيت قير + فلتر"),
            (3, "فحص كمبيوتر", "كهرباء", 120, "30 دقيقة", 7, "قراءة أكواد وتقرير"),
            (3, "تعبئة غاز تكييف", "تكييف", 180, "ساعة", 30, "فحص وتعبئة"),
        ]
        c.executemany("INSERT INTO services (partner_id,name,problem,price,duration,warranty_days,description) VALUES (?,?,?,?,?,?,?)", services)
        parts = [
            (4, "شل هيلكس 5W-30", "زيوت", 85, "4 لتر · شبه تخليقي", "ضمان المحل"),
            (4, "موبيل 1 5W-30", "زيوت", 165, "4 لتر · تخليقي كامل", "ضمان المحل"),
            (4, "أكوم 70 أمبير", "بطاريات", 380, "70A", "18 شهر"),
            (5, "بوش S5 90 أمبير", "بطاريات", 720, "90A", "36 شهر"),
            (5, "ميشلان Primacy 4", "كفرات", 520, "215/60R16", "ضمان المصنع"),
            (4, "بريدجستون Dueler", "كفرات", 550, "265/65R17", "ضمان المصنع"),
            (5, "فلتر زيت تويوتا", "فلاتر", 45, "أصلي", "ضمان المحل"),
        ]
        c.executemany("INSERT INTO parts (partner_id,name,category,price,meta,warranty) VALUES (?,?,?,?,?,?)", parts)
        c.execute("INSERT INTO users (phone, name, created_at) VALUES (?,?,?)",
                  ("0512345678", "عميل تجريبي", datetime.now().isoformat()))
        uid = c.lastrowid
        c.execute("INSERT INTO cars (user_id,brand,model,generation,year,color) VALUES (?,?,?,?,?,?)",
                  (uid, "تويوتا", "كامري", "2018-2024 (XV70)", "2021", "أبيض"))
        c.execute("""INSERT INTO orders (user_id,partner_id,title,type,price,delivery_fee,status,status_text,car_info,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (uid, 1, "تغيير زيت مكينة", "service", 280, 0, "active", "جاري التنفيذ", "كامري 2021", datetime.now().isoformat()))
        c.execute("""INSERT INTO orders (user_id,partner_id,title,type,price,delivery_fee,status,status_text,car_info,zone,created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (uid, 4, "بطارية أكوم 70 أمبير", "part", 380, 15, "new", "قيد المراجعة", "كامري 2021", "وسط الرياض", datetime.now().isoformat()))
        c.execute("INSERT INTO points_log (user_id,points,label,created_at) VALUES (?,?,?,?)",
                  (uid, 28, "طلب تجريبي", datetime.now().isoformat()))
        c.execute("INSERT INTO messages (order_id,sender,body,created_at) VALUES (?,?,?,?)",
                  (1, "workshop", "مرحباً، استلمنا طلبك وبدأنا الشغل", datetime.now().isoformat()))
    conn.commit()
    conn.close()

def j(rows):
    return [dict(r) for r in rows]

class App(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STATIC), **k)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
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

        # صفحات
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if path in ("/partner", "/partner.html"):
            return self._file(STATIC / "partner.html")

        # API
        if path == "/api/health":
            return self._send_json(200, {"ok": True, "service": "turbas"})

        if path == "/api/delivery-zones":
            return self._send_json(200, [
                {"id": "north", "name": "شمال الرياض", "fee": 25},
                {"id": "center", "name": "وسط الرياض", "fee": 15},
                {"id": "east", "name": "شرق الرياض", "fee": 20},
                {"id": "west", "name": "غرب الرياض", "fee": 22},
                {"id": "south", "name": "جنوب الرياض", "fee": 30},
            ])

        if path == "/api/partners":
            conn = get_db()
            data = j(conn.execute("SELECT id,name,phone,type,area FROM partners").fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/services":
            conn = get_db()
            q = """SELECT s.*, p.name as partner_name FROM services s
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
            q = """SELECT pt.*, p.name as partner_name FROM parts pt
                   JOIN partners p ON p.id=pt.partner_id WHERE 1=1"""
            params = []
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

        # ملفات static أخرى
        if path.startswith("/static/"):
            return self._file(STATIC / path[8:])
        f = STATIC / path.lstrip("/")
        if f.is_file():
            return self._file(f)
        return self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
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

        m = re.match(r"^/api/users/(\d+)/cars$", path)
        if m:
            uid = m.group(1)
            conn = get_db()
            conn.execute("INSERT INTO cars (user_id,brand,model,generation,year,color) VALUES (?,?,?,?,?,?)",
                         (uid, data.get("brand"), data.get("model"), data.get("generation"), data.get("year"), data.get("color")))
            conn.commit()
            cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": cid})

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
    print("=" * 50)
    print("  ترباس جاهز")
    print("  موقع العميل : http://127.0.0.1:%d" % PORT)
    print("  لوحة الورش  : http://127.0.0.1:%d/partner" % PORT)
    print("  API         : http://127.0.0.1:%d/api/health" % PORT)
    print("=" * 50)
    print("  دخول ورشة تجريبي: 0500000001")
    print("  دخول عميل تجريبي: 0512345678")
    print("=" * 50)
    HTTPServer((HOST, PORT), App).serve_forever()
