#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ترباس — Marketplace خدمات وقطع غيار السيارات"""
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

def j(rows):
    return [dict(r) for r in rows]

def now():
    return datetime.now().isoformat()

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
        user_id INTEGER, brand TEXT, model TEXT, year TEXT,
        trim TEXT, color TEXT, body TEXT, cylinders TEXT, fuel TEXT,
        is_default INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, phone TEXT UNIQUE, type TEXT DEFAULT 'workshop',
        area TEXT DEFAULT 'صناعية العاصمة',
        google_rating REAL DEFAULT 4.5,
        turbas_rating REAL DEFAULT 4.7,
        jobs_count INTEGER DEFAULT 0,
        warranty_ok INTEGER DEFAULT 1,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE, name TEXT, icon TEXT, sort INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS subcategories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER, slug TEXT, name TEXT, sort INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS service_defs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subcategory_id INTEGER, name TEXT, description TEXT,
        includes TEXT DEFAULT '', excludes TEXT DEFAULT '',
        sort INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, service_def_id INTEGER,
        price REAL, duration TEXT, warranty_days INTEGER DEFAULT 30,
        includes TEXT DEFAULT '', excludes TEXT DEFAULT '',
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, category TEXT, name TEXT, brand TEXT,
        grade TEXT DEFAULT 'تجاري', part_number TEXT DEFAULT '',
        price REAL, warranty TEXT, meta TEXT DEFAULT '',
        brands TEXT DEFAULT '', models TEXT DEFAULT '', years TEXT DEFAULT '',
        stock INTEGER DEFAULT 10, delivery INTEGER DEFAULT 1, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, partner_id INTEGER, offer_id INTEGER,
        product_id INTEGER, title TEXT, type TEXT DEFAULT 'service',
        price REAL, delivery_fee REAL DEFAULT 0,
        status TEXT DEFAULT 'paid', status_text TEXT DEFAULT 'تم الدفع',
        car_info TEXT, zone TEXT, vin TEXT, reveal INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS order_addons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, title TEXT, price REAL, reason TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, sender TEXT, body TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, points INTEGER, label TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS warranty_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, user_id INTEGER, reason TEXT,
        status TEXT DEFAULT 'open', created_at TEXT
    );
    """)

    if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        cats = [
            ("mechanics", "ميكانيكا", "🔧", 1),
            ("electrical", "كهرباء", "⚡", 2),
            ("cooling", "رديترات وتبريد", "🌡️", 3),
            ("body", "بدي", "🚗", 4),
            ("ac", "مكيف", "❄️", 5),
            ("brakes", "فرامل", "🛑", 6),
            ("tires", "إطارات", "🛞", 7),
            ("oils", "زيوت", "🛢️", 8),
            ("batteries", "بطاريات", "🔋", 9),
            ("parts", "قطع غيار", "⚙️", 10),
        ]
        c.executemany("INSERT INTO categories (slug,name,icon,sort) VALUES (?,?,?,?)", cats)

        subs = [
            # mechanics
            (1, "engine", "مكينة", 1), (1, "gearbox", "قير", 2), (1, "diff", "دفرنس", 3),
            (1, "mounts", "كراسي مكينة", 4), (1, "belts", "سيور", 5), (1, "water_pump", "مضخة ماء", 6),
            (1, "fuel_pump", "طرمبة بنزين", 7), (1, "cooling_sys", "نظام تبريد", 8),
            (1, "oil_leak", "تهريب زيوت", 9), (1, "engine_check", "فحص مكينة", 10),
            # electrical
            (2, "elec_check", "فحص كهرباء", 1), (2, "battery_svc", "بطارية", 2),
            (2, "alternator", "دينمو", 3), (2, "starter", "سلف", 4),
            (2, "sensors", "حساسات", 5), (2, "fuses", "فيوزات", 6),
            (2, "wiring", "أسلاك", 7), (2, "ecu", "كمبيوتر السيارة", 8),
            (2, "programming", "برمجة", 9), (2, "lights", "إنارة", 10),
            # cooling
            (3, "radiator", "رديتر", 1), (3, "rad_clean", "تنظيف رديتر", 2),
            (3, "rad_replace", "تغيير رديتر", 3), (3, "water_leak", "تهريب ماء", 4),
            (3, "thermo", "بلف حرارة", 5), (3, "fan", "مروحة", 6),
            (3, "cool_check", "فحص نظام التبريد", 7),
            # body
            (4, "bumper", "صدام", 1), (4, "fender", "رفرف", 2), (4, "hood", "كبوت", 3),
            (4, "door", "باب", 4), (4, "trunk", "شنطة", 5), (4, "bodywork", "سمكرة", 6),
            (4, "paint", "رش", 7), (4, "polish", "تلميع", 8),
            # ac
            (5, "ac_check", "فحص مكيف", 1), (5, "freon", "تعبئة فريون", 2),
            (5, "freon_leak", "تهريب فريون", 3), (5, "compressor", "كمبروسر", 4),
            (5, "ac_clean", "تنظيف مكيف", 5),
            # brakes
            (6, "pads_front", "تغيير فحمات أمامية", 1), (6, "pads_rear", "تغيير فحمات خلفية", 2),
            (6, "rotor_machine", "خرط هوبات", 3), (6, "rotor_replace", "تغيير هوبات", 4),
            (6, "brake_check", "فحص فرامل", 5), (6, "brake_fluid", "تغيير زيت فرامل", 6),
        ]
        c.executemany("INSERT INTO subcategories (category_id,slug,name,sort) VALUES (?,?,?,?)", subs)

        # service defs under subcategories (map by name lookup after insert)
        # We'll insert service_defs linked to subcategory ids
        # Get sub ids
        sub_map = {r["slug"]: r["id"] for r in c.execute("SELECT id,slug FROM subcategories").fetchall()}

        defs = [
            (sub_map["pads_front"], "تغيير فحمات أمامية", "استبدال فحمات الفرامل الأمامية", "فك وتركيب الفحمات · فحص أساسي للنظام", "الهوبات · قطع إضافية · إصلاحات أخرى"),
            (sub_map["pads_rear"], "تغيير فحمات خلفية", "استبدال فحمات الفرامل الخلفية", "فك وتركيب الفحمات · فحص أساسي", "الهوبات · قطع إضافية"),
            (sub_map["rotor_machine"], "خرط هوبات", "خرط أسطح الهوبات", "خرط الهوبات · فحص السماكة", "تغيير هوبات · فحمات"),
            (sub_map["rotor_replace"], "تغيير هوبات", "استبدال هوبات الفرامل", "توريد وتركيب هوبات", "فحمات · زيت فرامل"),
            (sub_map["brake_check"], "فحص فرامل", "فحص شامل لنظام الفرامل", "فحص الفحمات والهوبات والزيت", "استبدال قطع"),
            (sub_map["brake_fluid"], "تغيير زيت فرامل", "تفريغ وتعبئة زيت فرامل", "زيت فرامل · تفريغ هواء", "فحمات · هوبات"),
            (sub_map["engine_check"], "فحص مكينة", "فحص صوت وأداء المكينة", "فحص بصري · قراءة أكواد", "إصلاح · قطع"),
            (sub_map["oil_leak"], "كشف تهريب زيوت", "تحديد مصدر تهريب الزيت", "فحص وتنظيف وتحديد المصدر", "إصلاح · قطع"),
            (sub_map["water_pump"], "تغيير مضخة ماء", "استبدال مضخة الماء", "فك وتركيب · فحص السيور", "رديتر · بلف حرارة"),
            (sub_map["elec_check"], "فحص كهرباء", "فحص النظام الكهربائي", "قياس جهد · فحص فيوزات", "قطع · برمجة"),
            (sub_map["alternator"], "إصلاح/تغيير دينمو", "صيانة أو استبدال الدينمو", "فحص شحن · فك وتركيب", "بطارية · أسلاك"),
            (sub_map["starter"], "إصلاح/تغيير سلف", "صيانة أو استبدال السلف", "فحص · فك وتركيب", "بطارية"),
            (sub_map["ecu"], "فحص كمبيوتر السيارة", "قراءة أكواد وتشخيص", "تقرير أكواد", "برمجة · قطع"),
            (sub_map["rad_clean"], "تنظيف رديتر", "تنظيف رديتر ونظام التبريد", "تنظيف · تعبئة", "تغيير رديتر"),
            (sub_map["rad_replace"], "تغيير رديتر", "استبدال الرديتر", "توريد وتركيب · تعبئة", "طرمبة ماء"),
            (sub_map["cool_check"], "فحص نظام التبريد", "فحص ضغط وتهريب", "فحص ضغط · تقرير", "قطع"),
            (sub_map["freon"], "تعبئة فريون", "تعبئة غاز المكيف", "فحص ضغط · تعبئة", "كمبروسر · تهريب"),
            (sub_map["ac_check"], "فحص مكيف", "فحص تبريد المكيف", "قياس تبريد · تقرير", "قطع"),
            (sub_map["ac_clean"], "تنظيف مكيف", "تنظيف مجاري الهواء", "تنظيف · تعقيم", "فريون"),
            (sub_map["bodywork"], "سمكرة", "إصلاح صدمات وسمكرة", "سمكرة الجزء المتفق عليه", "رش كامل · قطع جديدة"),
            (sub_map["paint"], "رش قطعة", "رش قطعة بودي", "جهوزية ورش", "سمكرة إضافية"),
        ]
        c.executemany(
            "INSERT INTO service_defs (subcategory_id,name,description,includes,excludes) VALUES (?,?,?,?,?)",
            defs
        )

        partners = [
            ("ورشة النخبة", "0500000001", "workshop", "صناعية العاصمة", 4.6, 4.8, 127, 1),
            ("ورشة الإتقان", "0500000002", "workshop", "صناعية العاصمة", 4.4, 4.6, 84, 1),
            ("ورشة السرعة", "0500000003", "workshop", "صناعية العاصمة", 4.7, 4.9, 210, 1),
            ("محل قطع المعتمد", "0500000006", "parts", "صناعية العاصمة", 4.5, 4.7, 56, 1),
            ("محل البطاريات والزيوت", "0500000008", "parts", "صناعية العاصمة", 4.3, 4.5, 40, 1),
        ]
        c.executemany(
            "INSERT INTO partners (name,phone,type,area,google_rating,turbas_rating,jobs_count,warranty_ok) VALUES (?,?,?,?,?,?,?,?)",
            partners
        )

        # offers: multiple workshops for same services
        # service_def ids 1-6 brakes etc
        offers = [
            # pads front - 3 workshops
            (1, 1, 350, "45 دقيقة", 180, "فحمات · فك وتركيب · فحص", "هوبات"),
            (2, 1, 290, "50 دقيقة", 90, "فحمات · فك وتركيب", "هوبات · زيت"),
            (3, 1, 420, "40 دقيقة", 365, "فحمات سيراميك · فك وتركيب · فحص شامل", "لا شيء إضافي"),
            # pads rear
            (1, 2, 320, "45 دقيقة", 180, "فحمات خلفية · تركيب", "هوبات"),
            (2, 2, 270, "55 دقيقة", 90, "فحمات · تركيب", "هوبات"),
            (3, 2, 380, "40 دقيقة", 365, "فحمات ممتازة · تركيب وفحص", ""),
            # rotor machine
            (1, 3, 200, "60 دقيقة", 30, "خرط زوج هوبات", "فحمات"),
            (2, 3, 180, "70 دقيقة", 30, "خرط", "فحمات"),
            # brake check
            (1, 5, 80, "20 دقيقة", 7, "فحص شامل", "قطع"),
            (2, 5, 60, "25 دقيقة", 7, "فحص", "قطع"),
            (3, 5, 100, "15 دقيقة", 14, "فحص وتقرير", "قطع"),
            # engine check
            (1, 7, 120, "30 دقيقة", 7, "فحص وصوت وأكواد", "إصلاح"),
            (3, 7, 150, "25 دقيقة", 14, "فحص متقدم", "إصلاح"),
            # alternator
            (1, 11, 450, "ساعتين", 90, "فحص وإصلاح أو تبديل", "بطارية"),
            (2, 11, 380, "ساعتين", 60, "إصلاح/تبديل", "بطارية"),
            # radiator replace
            (1, 15, 550, "3 ساعات", 90, "رديتر · تركيب · تعبئة", "طرمبة"),
            (2, 15, 480, "3 ساعات", 60, "رديتر · تركيب", "طرمبة"),
            # freon
            (1, 17, 250, "45 دقيقة", 30, "فحص وتعبئة", "كمبروسر"),
            (3, 17, 280, "40 دقيقة", 60, "تعبئة وفحص تهريب", "كمبروسر"),
            # ac check
            (2, 18, 90, "20 دقيقة", 7, "فحص تبريد", "قطع"),
            (3, 18, 110, "20 دقيقة", 14, "فحص وتقرير", "قطع"),
        ]
        c.executemany(
            "INSERT INTO offers (partner_id,service_def_id,price,duration,warranty_days,includes,excludes) VALUES (?,?,?,?,?,?,?)",
            offers
        )

        products = [
            (4, "فلاتر", "فلتر زيت تويوتا أصلي", "تويوتا", "أصلي", "90915-YZZD2", 45, "ضمان المحل", "OEM", "تويوتا", "كامري,كورولا", "2018-2024"),
            (4, "فلاتر", "فلتر هواء هيونداي", "هيونداي", "درجة أولى", "28113-F2000", 55, "ضمان المحل", "", "هيونداي", "النترا,سوناتا", "2016-2024"),
            (5, "زيوت", "شل هيلكس 5W-30", "شل", "درجة أولى", "SHX530", 85, "ضمان المحل", "4 لتر", "تويوتا,هيونداي", "كامري,النترا", "2015-2024"),
            (5, "زيوت", "موبيل 1 5W-30", "موبيل", "أصلي", "M1530", 165, "ضمان المحل", "4 لتر كامل", "تويوتا,لكزس", "كامري,ES", "2015-2024"),
            (5, "بطاريات", "أكوم 70 أمبير", "أكوم", "تجاري", "AC70", 380, "18 شهر", "70A", "تويوتا,نيسان", "كامري,التيما", "2012-2024"),
            (5, "بطاريات", "بوش S5 90 أمبير", "بوش", "أصلي", "BOSCHS590", 720, "36 شهر", "90A", "شيفروليه,جمس", "تاهو,يوكون", "2015-2024"),
            (4, "كفرات", "ميشلان Primacy 4 215/60R16", "ميشلان", "أصلي", "PRIM215", 520, "ضمان المصنع", "215/60R16", "تويوتا,هيونداي", "كامري,النترا", "2015-2024"),
            (4, "كفرات", "بريدجستون 265/65R17", "بريدجستون", "درجة أولى", "BR265", 550, "ضمان المصنع", "265/65R17", "تويوتا,نيسان", "لاندكروزر,باترول", "2010-2024"),
        ]
        c.executemany(
            """INSERT INTO products (partner_id,category,name,brand,grade,part_number,price,warranty,meta,brands,models,years)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", products
        )

        c.execute("INSERT INTO users (phone,name,created_at) VALUES (?,?,?)",
                  ("0512345678", "عميل تجريبي", now()))
        uid = c.lastrowid
        c.execute("""INSERT INTO cars (user_id,brand,model,year,trim,color,body,cylinders,fuel,is_default)
                     VALUES (?,?,?,?,?,?,?,?,?,1)""",
                  (uid, "تويوتا", "كامري", "2020", "LE", "أبيض", "سيدان", "4", "بنزين"))
        c.execute("INSERT INTO points_log (user_id,points,label,created_at) VALUES (?,?,?,?)",
                  (uid, 28, "ترحيب", now()))

    conn.commit()
    conn.close()

class App(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STATIC), **k)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS,DELETE,PUT")
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
            return self._send_json(200, {"ok": True, "service": "turbas", "version": "2.0"})

        if path == "/api/delivery-zones":
            return self._send_json(200, [
                {"id": "sinaeya", "name": "صناعية العاصمة", "fee": 0},
                {"id": "nearby", "name": "أحياء قريبة من الصناعية", "fee": 25},
                {"id": "riyadh", "name": "باقي الرياض", "fee": 35},
            ])

        if path == "/api/categories":
            conn = get_db()
            data = j(conn.execute("SELECT * FROM categories ORDER BY sort").fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/subcategories":
            conn = get_db()
            q = "SELECT * FROM subcategories WHERE 1=1"
            params = []
            if "category_id" in qs:
                q += " AND category_id=?"; params.append(qs["category_id"][0])
            q += " ORDER BY sort"
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/services":
            # service definitions, optional subcategory filter
            conn = get_db()
            q = """SELECT sd.*, sc.name as subcategory_name, sc.category_id, c.name as category_name, c.slug as category_slug
                   FROM service_defs sd
                   JOIN subcategories sc ON sc.id=sd.subcategory_id
                   JOIN categories c ON c.id=sc.category_id WHERE 1=1"""
            params = []
            if "subcategory_id" in qs:
                q += " AND sd.subcategory_id=?"; params.append(qs["subcategory_id"][0])
            if "category_id" in qs:
                q += " AND sc.category_id=?"; params.append(qs["category_id"][0])
            q += " ORDER BY sd.sort, sd.id"
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/offers":
            # marketplace offers — NO partner name unless reveal
            conn = get_db()
            q = """SELECT o.id, o.service_def_id, o.price, o.duration, o.warranty_days,
                          o.includes, o.excludes, o.active,
                          p.turbas_rating, p.google_rating, p.jobs_count, p.warranty_ok, p.area,
                          sd.name as service_name, sd.description, sd.includes as def_includes, sd.excludes as def_excludes
                   FROM offers o
                   JOIN partners p ON p.id=o.partner_id
                   JOIN service_defs sd ON sd.id=o.service_def_id
                   WHERE o.active=1 AND p.active=1"""
            params = []
            if "service_def_id" in qs:
                q += " AND o.service_def_id=?"; params.append(qs["service_def_id"][0])
            if "partner_id" in qs:
                # partner panel — include name
                q = """SELECT o.*, p.name as partner_name, sd.name as service_name
                       FROM offers o JOIN partners p ON p.id=o.partner_id
                       JOIN service_defs sd ON sd.id=o.service_def_id
                       WHERE o.partner_id=?"""
                params = [qs["partner_id"][0]]
            data = j(conn.execute(q, params).fetchall())
            # default sort by turbas_rating * log(jobs) value score
            if "partner_id" not in qs:
                def score(x):
                    return (x.get("turbas_rating") or 0) * 20 + (x.get("jobs_count") or 0) * 0.05 - (x.get("price") or 0) * 0.01
                data.sort(key=score, reverse=True)
            conn.close()
            return self._send_json(200, data)

        if path == "/api/products":
            conn = get_db()
            q = """SELECT pt.id, pt.partner_id, pt.category, pt.name, pt.brand, pt.grade, pt.part_number,
                          pt.price, pt.warranty, pt.meta, pt.brands, pt.models, pt.years,
                          pt.stock, pt.delivery, p.area, p.turbas_rating
                   FROM products pt JOIN partners p ON p.id=pt.partner_id
                   WHERE pt.active=1"""
            params = []
            if "category" in qs and qs["category"][0] != "الكل":
                q += " AND pt.category=?"; params.append(qs["category"][0])
            if "partner_id" in qs:
                q = """SELECT pt.*, p.name as partner_name FROM products pt
                       JOIN partners p ON p.id=pt.partner_id WHERE pt.partner_id=?"""
                params = [qs["partner_id"][0]]
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/partners":
            conn = get_db()
            # public: limited; with phone login partner sees self
            if "phone" in qs:
                row = conn.execute("SELECT * FROM partners WHERE phone=?", (qs["phone"][0],)).fetchone()
                conn.close()
                if not row: return self._send_json(404, {"error": "غير مسجل"})
                return self._send_json(200, dict(row))
            data = j(conn.execute("SELECT id,type,area,turbas_rating,google_rating,jobs_count FROM partners WHERE active=1").fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/orders":
            conn = get_db()
            q = "SELECT o.* FROM orders o WHERE 1=1"
            params = []
            if "user_id" in qs:
                q += " AND o.user_id=?"; params.append(qs["user_id"][0])
            if "partner_id" in qs:
                q += " AND o.partner_id=?"; params.append(qs["partner_id"][0])
            if "status" in qs:
                q += " AND o.status=?"; params.append(qs["status"][0])
            q += " ORDER BY o.id DESC"
            rows = j(conn.execute(q, params).fetchall())
            # reveal name only if paid/reveal
            for r in rows:
                if r.get("reveal") or r.get("status") in ("paid","confirmed","in_progress","done"):
                    p = conn.execute("SELECT name,area,phone FROM partners WHERE id=?", (r["partner_id"],)).fetchone()
                    if p:
                        r["partner_name"] = p["name"]
                        r["partner_area"] = p["area"]
                        if r.get("reveal"):
                            r["partner_phone"] = p["phone"]
                else:
                    r["partner_name"] = "مقدم خدمة"
            conn.close()
            return self._send_json(200, rows)

        m = re.match(r"^/api/orders/(\d+)$", path)
        if m:
            conn = get_db()
            r = conn.execute("SELECT * FROM orders WHERE id=?", (m.group(1),)).fetchone()
            if not r:
                conn.close(); return self._send_json(404, {"error": "not found"})
            r = dict(r)
            if r.get("reveal") or r.get("status") in ("paid","confirmed","in_progress","done"):
                p = conn.execute("SELECT name,area,phone FROM partners WHERE id=?", (r["partner_id"],)).fetchone()
                if p:
                    r["partner_name"] = p["name"]; r["partner_area"] = p["area"]
                    if r.get("reveal"): r["partner_phone"] = p["phone"]
            addons = j(conn.execute("SELECT * FROM order_addons WHERE order_id=?", (m.group(1),)).fetchall())
            r["addons"] = addons
            conn.close()
            return self._send_json(200, r)

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM messages WHERE order_id=? ORDER BY id", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/users/(\d+)/cars$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM cars WHERE user_id=? ORDER BY is_default DESC, id", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/users/(\d+)/points$", path)
        if m:
            conn = get_db()
            uid = m.group(1)
            log = j(conn.execute("SELECT * FROM points_log WHERE user_id=? ORDER BY id DESC LIMIT 50", (uid,)).fetchall())
            total = conn.execute("SELECT COALESCE(SUM(points),0) FROM points_log WHERE user_id=?", (uid,)).fetchone()[0]
            conn.close()
            return self._send_json(200, {"total": total, "log": log, "next_reward_at": 100, "remaining": max(0, 100 - (total % 100))})

        if path == "/api/partner/stats":
            pid = qs.get("partner_id", [None])[0]
            if not pid: return self._send_json(400, {"error": "partner_id"})
            conn = get_db()
            orders = j(conn.execute("SELECT * FROM orders WHERE partner_id=?", (pid,)).fetchall())
            sales = sum(o["price"] or 0 for o in orders if o["status"] != "cancelled")
            commission = round(sales * 0.15, 2)
            stats = {
                "new": sum(1 for o in orders if o["status"] in ("paid","new")),
                "confirmed": sum(1 for o in orders if o["status"] == "confirmed"),
                "in_progress": sum(1 for o in orders if o["status"] == "in_progress"),
                "done": sum(1 for o in orders if o["status"] == "done"),
                "sales": sales,
                "commission": commission,
                "net": round(sales - commission, 2),
            }
            conn.close()
            return self._send_json(200, stats)

        f = STATIC / path.lstrip("/")
        if f.is_file():
            return self._file(f)
        return self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()

        if path == "/api/auth/login":
            phone = (data.get("phone") or "").strip() or "0512345678"
            conn = get_db()
            row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (phone,name,created_at) VALUES (?,?,?)",
                             (phone, data.get("name") or "عميل", now()))
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

        if path == "/api/cars":
            conn = get_db()
            if data.get("is_default"):
                conn.execute("UPDATE cars SET is_default=0 WHERE user_id=?", (data["user_id"],))
            conn.execute("""INSERT INTO cars (user_id,brand,model,year,trim,color,body,cylinders,fuel,is_default)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (data["user_id"], data.get("brand"), data.get("model"), data.get("year"),
                          data.get("trim"), data.get("color"), data.get("body"), data.get("cylinders"),
                          data.get("fuel"), 1 if data.get("is_default") else 0))
            conn.commit()
            cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": cid})

        if path == "/api/offers":
            conn = get_db()
            conn.execute("""INSERT INTO offers (partner_id,service_def_id,price,duration,warranty_days,includes,excludes,active)
                            VALUES (?,?,?,?,?,?,?,1)""",
                         (data["partner_id"], data["service_def_id"], data.get("price", 0),
                          data.get("duration") or "", data.get("warranty_days", 30),
                          data.get("includes") or "", data.get("excludes") or ""))
            conn.commit()
            oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": oid})

        if path == "/api/products":
            conn = get_db()
            conn.execute("""INSERT INTO products
                (partner_id,category,name,brand,grade,part_number,price,warranty,meta,brands,models,years,stock,delivery,active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (data["partner_id"], data.get("category") or "فلاتر", data.get("name"),
                 data.get("brand") or "", data.get("grade") or "تجاري", data.get("part_number") or "",
                 data.get("price", 0), data.get("warranty") or "", data.get("meta") or "",
                 data.get("brands") or "", data.get("models") or "", data.get("years") or "",
                 data.get("stock", 10), 1 if data.get("delivery", True) else 0))
            conn.commit()
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": pid})

        if path == "/api/orders":
            # create order = "payment" in prototype → reveal partner
            conn = get_db()
            partner_id = data.get("partner_id")
            offer_id = data.get("offer_id")
            if offer_id and not partner_id:
                off = conn.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
                if off:
                    partner_id = off["partner_id"]
                    data.setdefault("price", off["price"])
                    data.setdefault("title", conn.execute("SELECT name FROM service_defs WHERE id=?", (off["service_def_id"],)).fetchone()["name"])
            if data.get("product_id") and not partner_id:
                pr = conn.execute("SELECT * FROM products WHERE id=?", (data["product_id"],)).fetchone()
                if pr:
                    partner_id = pr["partner_id"]
                    data.setdefault("price", pr["price"])
                    data.setdefault("title", pr["name"])
            conn.execute("""INSERT INTO orders
                (user_id,partner_id,offer_id,product_id,title,type,price,delivery_fee,status,status_text,car_info,zone,vin,reveal,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (data.get("user_id"), partner_id, offer_id, data.get("product_id"),
                 data.get("title"), data.get("type", "service"), data.get("price", 0),
                 data.get("delivery_fee", 0), "paid", "تم الدفع",
                 data.get("car_info"), data.get("zone"), data.get("vin"), now()))
            conn.commit()
            oid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            pts = int((data.get("price") or 0) // 10)
            if pts and data.get("user_id"):
                conn.execute("INSERT INTO points_log (user_id,points,label,created_at) VALUES (?,?,?,?)",
                             (data["user_id"], pts, "طلب #%s" % oid, now()))
                conn.commit()
            # bump jobs
            if partner_id:
                conn.execute("UPDATE partners SET jobs_count=jobs_count+1 WHERE id=?", (partner_id,))
                conn.commit()
            p = conn.execute("SELECT name,area,phone FROM partners WHERE id=?", (partner_id,)).fetchone()
            conn.close()
            return self._send_json(201, {
                "id": oid, "points_earned": pts,
                "partner_name": p["name"] if p else None,
                "partner_area": p["area"] if p else None,
                "partner_phone": p["phone"] if p else None,
            })

        m = re.match(r"^/api/orders/(\d+)/status$", path)
        if m:
            oid = m.group(1)
            st = data.get("status") or "confirmed"
            text_map = {
                "paid": "تم الدفع", "confirmed": "مؤكد", "in_progress": "قيد التنفيذ",
                "done": "مكتمل", "cancelled": "ملغي",
            }
            text = data.get("status_text") or text_map.get(st, st)
            conn = get_db()
            conn.execute("UPDATE orders SET status=?, status_text=?, reveal=1 WHERE id=?", (st, text, oid))
            conn.commit(); conn.close()
            return self._send_json(200, {"ok": True, "status": st, "status_text": text})

        m = re.match(r"^/api/orders/(\d+)/addons$", path)
        if m:
            oid = m.group(1)
            conn = get_db()
            conn.execute("""INSERT INTO order_addons (order_id,title,price,reason,status,created_at)
                            VALUES (?,?,?,?,'pending',?)""",
                         (oid, data.get("title"), data.get("price", 0), data.get("reason") or "", now()))
            conn.commit()
            aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": aid})

        m = re.match(r"^/api/orders/(\d+)/addons/(\d+)$", path)
        if m:
            oid, aid = m.group(1), m.group(2)
            action = data.get("action")  # accept / reject
            conn = get_db()
            if action == "accept":
                ad = conn.execute("SELECT * FROM order_addons WHERE id=?", (aid,)).fetchone()
                conn.execute("UPDATE order_addons SET status='accepted' WHERE id=?", (aid,))
                if ad:
                    conn.execute("UPDATE orders SET price=price+? WHERE id=?", (ad["price"], oid))
                    # commission already on total conceptually
                conn.commit()
            else:
                conn.execute("UPDATE order_addons SET status='rejected' WHERE id=?", (aid,))
                conn.commit()
            conn.close()
            return self._send_json(200, {"ok": True})

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            oid = m.group(1)
            conn = get_db()
            conn.execute("INSERT INTO messages (order_id,sender,body,created_at) VALUES (?,?,?,?)",
                         (oid, data.get("sender", "customer"), data.get("body", ""), now()))
            conn.commit()
            mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": mid})

        if path == "/api/warranty":
            conn = get_db()
            conn.execute("""INSERT INTO warranty_claims (order_id,user_id,reason,status,created_at)
                            VALUES (?,?,?,'open',?)""",
                         (data.get("order_id"), data.get("user_id"), data.get("reason") or "", now()))
            conn.commit()
            cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": cid})

        return self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        m = re.match(r"^/api/offers/(\d+)$", path)
        if m:
            conn = get_db(); conn.execute("DELETE FROM offers WHERE id=?", (m.group(1),)); conn.commit(); conn.close()
            return self._send_json(200, {"ok": True})
        m = re.match(r"^/api/products/(\d+)$", path)
        if m:
            conn = get_db(); conn.execute("DELETE FROM products WHERE id=?", (m.group(1),)); conn.commit(); conn.close()
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
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

if __name__ == "__main__":
    init_db()
    print("ترباس v2 → http://0.0.0.0:%d" % PORT)
    HTTPServer((HOST, PORT), App).serve_forever()
