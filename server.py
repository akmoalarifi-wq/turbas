#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ترباس v3 — Marketplace خدمات ومنتجات السيارات"""
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
DB = Path(os.environ.get("TURBAS_DB", str(ROOT / "data" / "turbas.db")))
try:
    DB.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    DB = Path("/tmp") / "turbas.db"


PREFIX = {"workshop": "WR", "parts": "PR", "batteries": "BT", "oils": "OI", "tires": "TY"}

def get_db():
    conn = sqlite3.connect(str(DB), check_same_thread=False)
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
        body TEXT, trim TEXT, engine TEXT, cylinders TEXT, fuel TEXT,
        transmission TEXT, color TEXT, is_default INTEGER DEFAULT 0,
        plate TEXT DEFAULT '', odometer INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS partners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, name TEXT, phone TEXT UNIQUE,
        type TEXT DEFAULT 'workshop',
        area TEXT DEFAULT 'صناعية العاصمة',
        google_rating REAL DEFAULT 4.5,
        turbas_rating REAL DEFAULT 4.7,
        jobs_count INTEGER DEFAULT 0,
        warranty_ok INTEGER DEFAULT 1,
        active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id INTEGER DEFAULT 0,
        slug TEXT, name TEXT, icon TEXT, sort INTEGER DEFAULT 0,
        scope TEXT DEFAULT 'workshop'
    );
    CREATE TABLE IF NOT EXISTS service_defs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER, name TEXT, description TEXT,
        includes TEXT DEFAULT '', excludes TEXT DEFAULT '', sort INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, service_def_id INTEGER,
        price REAL, duration TEXT, warranty_days INTEGER DEFAULT 30,
        includes TEXT DEFAULT '', excludes TEXT DEFAULT '', active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        partner_id INTEGER, kind TEXT,
        name TEXT, brand TEXT, grade TEXT DEFAULT 'تجاري',
        part_number TEXT DEFAULT '', price REAL, warranty TEXT,
        meta TEXT DEFAULT '', brands TEXT DEFAULT '', models TEXT DEFAULT '',
        years TEXT DEFAULT '',
        width TEXT DEFAULT '', aspect TEXT DEFAULT '', rim TEXT DEFAULT '',
        viscosity TEXT DEFAULT '', volume TEXT DEFAULT '',
        cca TEXT DEFAULT '', size_code TEXT DEFAULT '',
        stock INTEGER DEFAULT 10, delivery INTEGER DEFAULT 1, active INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS vehicle_brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, name_en TEXT, sort INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS vehicle_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand_id INTEGER, name TEXT, name_en TEXT,
        years TEXT, bodies TEXT DEFAULT '', trims TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, partner_id INTEGER, offer_id INTEGER,
        product_id INTEGER, title TEXT, type TEXT DEFAULT 'service',
        price REAL, delivery_fee REAL DEFAULT 0,
        status TEXT DEFAULT 'paid', status_text TEXT DEFAULT 'تم الدفع',
        car_info TEXT, zone TEXT, vin TEXT, reveal INTEGER DEFAULT 1,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS order_addons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, title TEXT, price REAL, reason TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER, sender TEXT, body TEXT,
        msg_type TEXT DEFAULT 'text', created_at TEXT
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
    CREATE TABLE IF NOT EXISTS service_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car_id INTEGER, order_id INTEGER, title TEXT, price REAL,
        partner_name TEXT, done_at TEXT, odometer INTEGER DEFAULT 0, notes TEXT
    );
    """)

    if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        # root workshop service categories (parent_id=0, scope=workshop)
        roots = [
            ("mechanics", "ميكانيكا", "🔧", 1),
            ("electrical", "كهرباء", "⚡", 2),
            ("cooling", "رديترات وتبريد", "🌡️", 3),
            ("body", "بدي وسمكرة", "🚗", 4),
            ("ac", "مكيف", "❄️", 5),
            ("brakes", "فرامل", "🛑", 6),
            ("suspension", "تعليق وعفشة", "🔩", 7),
            ("diagnostics", "فحص وتشخيص", "🔍", 8),
            ("programming", "برمجة وكمبيوتر", "💻", 9),
        ]
        for slug, name, icon, sort in roots:
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (0,?,?,?,?, 'workshop')",
                      (slug, name, icon, sort))

        # sub under mechanics
        mech = c.execute("SELECT id FROM categories WHERE slug='mechanics'").fetchone()[0]
        for i, (slug, name) in enumerate([
            ("engine", "مكينة"), ("gearbox", "قير"), ("diff", "دفرنس"),
            ("belts", "سيور"), ("mounts", "كراسي مكينة"), ("water_pump", "طرمبة ماء"),
            ("fuel_pump", "طرمبة بنزين"), ("oil_leak", "تهريب زيوت"),
            ("engine_check", "فحص مكينة"), ("engine_repair", "إصلاح مكينة"),
            ("engine_rebuild", "توضيب مكينة"),
        ], 1):
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (?,?,?,?,?,'workshop')",
                      (mech, slug, name, "", i))

        brakes = c.execute("SELECT id FROM categories WHERE slug='brakes'").fetchone()[0]
        for i, (slug, name) in enumerate([
            ("pads_front", "فحمات أمامية"), ("pads_rear", "فحمات خلفية"),
            ("rotors", "هوبات"), ("brake_fluid", "زيت فرامل"), ("brake_check", "فحص فرامل"),
        ], 1):
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (?,?,?,?,?,'workshop')",
                      (brakes, slug, name, "", i))

        elec = c.execute("SELECT id FROM categories WHERE slug='electrical'").fetchone()[0]
        for i, (slug, name) in enumerate([
            ("battery_svc", "بطارية"), ("alternator", "دينمو"), ("starter", "سلف"),
            ("sensors", "حساسات"), ("wiring", "أسلاك"), ("lights", "إنارة"),
        ], 1):
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (?,?,?,?,?,'workshop')",
                      (elec, slug, name, "", i))

        cool = c.execute("SELECT id FROM categories WHERE slug='cooling'").fetchone()[0]
        for i, (slug, name) in enumerate([
            ("radiator", "رديتر"), ("thermo", "بلف حرارة"), ("fan", "مروحة"), ("cool_check", "فحص تبريد"),
        ], 1):
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (?,?,?,?,?,'workshop')",
                      (cool, slug, name, "", i))

        ac = c.execute("SELECT id FROM categories WHERE slug='ac'").fetchone()[0]
        for i, (slug, name) in enumerate([
            ("freon", "فريون"), ("compressor", "كمبروسر"), ("ac_clean", "تنظيف مكيف"), ("ac_check", "فحص مكيف"),
        ], 1):
            c.execute("INSERT INTO categories (parent_id,slug,name,icon,sort,scope) VALUES (?,?,?,?,?,'workshop')",
                      (ac, slug, name, "", i))

        # service defs linked to leaf categories
        def add_svc(cat_slug, name, desc, inc, exc):
            row = c.execute("SELECT id FROM categories WHERE slug=?", (cat_slug,)).fetchone()
            if not row: return
            c.execute("INSERT INTO service_defs (category_id,name,description,includes,excludes) VALUES (?,?,?,?,?)",
                      (row[0], name, desc, inc, exc))

        add_svc("pads_front", "تغيير فحمات أمامية", "استبدال فحمات الفرامل الأمامية",
                "فك وتركيب الفحمات · فحص أساسي للنظام", "الهوبات · قطع إضافية · إصلاحات أخرى")
        add_svc("pads_rear", "تغيير فحمات خلفية", "استبدال فحمات الفرامل الخلفية",
                "فك وتركيب · فحص أساسي", "الهوبات · قطع إضافية")
        add_svc("rotors", "خرط هوبات", "خرط أسطح الهوبات", "خرط زوج · فحص السماكة", "فحمات · استبدال هوبات")
        add_svc("rotors", "تغيير هوبات", "استبدال هوبات", "توريد وتركيب", "فحمات · زيت فرامل")
        add_svc("brake_check", "فحص فرامل", "فحص شامل لنظام الفرامل", "فحص الفحمات والهوبات والزيت", "استبدال قطع")
        add_svc("brake_fluid", "تغيير زيت فرامل", "تفريغ وتعبئة زيت فرامل", "زيت · تفريغ هواء", "فحمات · هوبات")
        add_svc("engine_check", "فحص مكينة", "فحص صوت وأداء وقراءة أكواد", "فحص بصري · تقرير أكواد", "إصلاح · قطع")
        add_svc("engine_repair", "إصلاح مكينة", "إصلاح أعطال المكينة حسب التشخيص", "حسب الاتفاق", "توضيب كامل")
        add_svc("engine_rebuild", "توضيب مكينة", "توضيب كامل للمكينة", "حسب الاتفاق والعقد", "قطع خارج النطاق")
        add_svc("oil_leak", "كشف تهريب زيوت", "تحديد مصدر التهريب", "فحص وتنظيف وتحديد المصدر", "إصلاح · قطع")
        add_svc("water_pump", "تغيير طرمبة ماء", "استبدال مضخة الماء", "فك وتركيب · فحص السيور", "رديتر")
        add_svc("alternator", "إصلاح/تغيير دينمو", "صيانة أو استبدال", "فحص شحن · فك وتركيب", "بطارية")
        add_svc("starter", "إصلاح/تغيير سلف", "صيانة أو استبدال السلف", "فحص · فك وتركيب", "بطارية")
        add_svc("radiator", "تغيير رديتر", "استبدال الرديتر", "توريد وتركيب · تعبئة", "طرمبة ماء")
        add_svc("radiator", "تنظيف رديتر", "تنظيف نظام التبريد", "تنظيف · تعبئة", "تغيير رديتر")
        add_svc("freon", "تعبئة فريون", "تعبئة غاز المكيف", "فحص ضغط · تعبئة", "كمبروسر · تهريب")
        add_svc("ac_check", "فحص مكيف", "فحص تبريد", "قياس تبريد · تقرير", "قطع")
        add_svc("ac_clean", "تنظيف مكيف", "تنظيف وتعقيم مجاري", "تنظيف · تعقيم", "فريون")

        # partners
        partners = [
            ("WR-1001", "ورشة النخبة", "0500000001", "workshop", 4.6, 4.8, 127),
            ("WR-1002", "ورشة الإتقان", "0500000002", "workshop", 4.4, 4.6, 84),
            ("WR-1003", "ورشة السرعة", "0500000003", "workshop", 4.7, 4.9, 210),
            ("PR-2001", "محل قطع المعتمد", "0500000006", "parts", 4.5, 4.7, 56),
            ("BT-3001", "مركز البطاريات", "0500000008", "batteries", 4.3, 4.5, 40),
            ("OI-4001", "محل الزيوت الذهبي", "0500000009", "oils", 4.4, 4.6, 33),
            ("TY-5001", "كفرات الرياض", "0500000010", "tires", 4.5, 4.7, 48),
        ]
        for code, name, phone, typ, gr, tr, jobs in partners:
            c.execute("""INSERT INTO partners (code,name,phone,type,area,google_rating,turbas_rating,jobs_count,warranty_ok)
                         VALUES (?,?,?,?, 'صناعية العاصمة',?,?,?,1)""",
                      (code, name, phone, typ, gr, tr, jobs))

        # offers multi-workshop for key services
        sd = {r["name"]: r["id"] for r in c.execute("SELECT id,name FROM service_defs").fetchall()}
        def off(pid, sname, price, dur, war, inc, exc):
            sid = sd.get(sname)
            if not sid: return
            c.execute("""INSERT INTO offers (partner_id,service_def_id,price,duration,warranty_days,includes,excludes)
                         VALUES (?,?,?,?,?,?,?)""", (pid, sid, price, dur, war, inc, exc))

        off(1, "تغيير فحمات أمامية", 350, "45 دقيقة", 180, "فحمات · فك وتركيب · فحص", "هوبات")
        off(2, "تغيير فحمات أمامية", 290, "50 دقيقة", 90, "فحمات · فك وتركيب", "هوبات · زيت")
        off(3, "تغيير فحمات أمامية", 420, "40 دقيقة", 365, "فحمات سيراميك · فحص شامل", "لا شيء إضافي")
        off(1, "تغيير فحمات خلفية", 320, "45 دقيقة", 180, "فحمات خلفية · تركيب", "هوبات")
        off(2, "تغيير فحمات خلفية", 270, "55 دقيقة", 90, "فحمات · تركيب", "هوبات")
        off(3, "تغيير فحمات خلفية", 380, "40 دقيقة", 365, "فحمات ممتازة · فحص", "")
        off(1, "فحص فرامل", 80, "20 دقيقة", 7, "فحص شامل", "قطع")
        off(2, "فحص فرامل", 60, "25 دقيقة", 7, "فحص", "قطع")
        off(3, "فحص فرامل", 100, "15 دقيقة", 14, "فحص وتقرير", "قطع")
        off(1, "فحص مكينة", 120, "30 دقيقة", 7, "فحص وأكواد", "إصلاح")
        off(3, "فحص مكينة", 150, "25 دقيقة", 14, "فحص متقدم", "إصلاح")
        off(1, "تغيير رديتر", 550, "3 ساعات", 90, "رديتر · تركيب · تعبئة", "طرمبة")
        off(2, "تغيير رديتر", 480, "3 ساعات", 60, "رديتر · تركيب", "طرمبة")
        off(1, "تعبئة فريون", 250, "45 دقيقة", 30, "فحص وتعبئة", "كمبروسر")
        off(3, "تعبئة فريون", 280, "40 دقيقة", 60, "تعبئة وفحص تهريب", "كمبروسر")
        off(1, "إصلاح/تغيير دينمو", 450, "ساعتين", 90, "فحص وإصلاح أو تبديل", "بطارية")
        off(2, "إصلاح/تغيير دينمو", 380, "ساعتين", 60, "إصلاح/تبديل", "بطارية")

        # products
        prods = [
            (4, "parts", "فلتر زيت تويوتا أصلي", "تويوتا", "أصلي", "90915-YZZD2", 45, "ضمان المحل", "", "تويوتا", "كامري,كورولا", "2018-2024"),
            (4, "parts", "فلتر هواء هيونداي", "هيونداي", "درجة أولى", "28113-F2000", 55, "ضمان المحل", "", "هيونداي", "النترا", "2016-2024"),
            (6, "oils", "شل هيلكس 5W-30", "شل", "درجة أولى", "SHX530", 85, "ضمان المحل", "5W-30", "تويوتا,هيونداي", "كامري,النترا", "2015-2024"),
            (6, "oils", "موبيل 1 5W-30", "موبيل", "أصلي", "M1530", 165, "ضمان المحل", "5W-30", "تويوتا,لكزس", "كامري,ES", "2015-2024"),
            (5, "batteries", "أكوم 70 أمبير", "أكوم", "تجاري", "AC70", 380, "18 شهر", "70A", "تويوتا,نيسان", "كامري,التيما", "2012-2024"),
            (5, "batteries", "بوش S5 90 أمبير", "بوش", "أصلي", "BOSCHS590", 720, "36 شهر", "90A", "شيفروليه,جمس", "تاهو,سييرا", "2015-2024"),
            (7, "tires", "ميشلان Primacy 4", "ميشلان", "أصلي", "PRIM215", 520, "ضمان المصنع", "215/60R16", "تويوتا,هيونداي", "كامري,النترا", "2015-2024"),
            (7, "tires", "بريدجستون دويلر", "بريدجستون", "درجة أولى", "BR265", 550, "ضمان المصنع", "265/65R17", "تويوتا,نيسان,جمس", "لاندكروزر,سييرا", "2010-2024"),
        ]
        for pid, kind, name, brand, grade, pnum, price, war, meta, brands, models, years in prods:
            w = a = r = vis = vol = cca = size = ""
            if kind == "tires" and "/" in meta:
                # 215/60R16
                parts = meta.replace("R", "/").split("/")
                if len(parts) >= 3:
                    w, a, r = parts[0], parts[1], parts[2]
            if kind == "oils":
                vis = meta; vol = "4 لتر"
            if kind == "batteries":
                cca = meta; size = meta
            c.execute("""INSERT INTO products
                (partner_id,kind,name,brand,grade,part_number,price,warranty,meta,brands,models,years,
                 width,aspect,rim,viscosity,volume,cca,size_code,stock,delivery,active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,10,1,1)""",
                (pid, kind, name, brand, grade, pnum, price, war, meta, brands, models, years,
                 w, a, r, vis, vol, cca, size))

        # vehicle catalog
        brands_data = [
            ("تويوتا", "Toyota", 1, [
                ("كامري", "Camry", "2015-2026", "سيدان", "LE,SE,XLE,XSE,Hybrid"),
                ("كورولا", "Corolla", "2015-2026", "سيدان,هاتشباك", "Base,SE,XLE"),
                ("لاندكروزر", "Land Cruiser", "2010-2026", "SUV", "GXR,VXR,VX"),
                ("هايلكس", "Hilux", "2015-2026", "بيك أب غمارة,بيك أب غمارتين", "GLX,Adventure"),
            ]),
            ("جمس", "GMC", 2, [
                ("سييرا", "Sierra", "2019-2026", "بيك أب غمارة,بيك أب غمارتين", "SLE,SLT,AT4,AT4X,Denali"),
                ("يوكون", "Yukon", "2015-2026", "SUV", "SLE,SLT,AT4,Denali"),
                ("أكاديا", "Acadia", "2017-2026", "SUV", "SLE,SLT,Denali"),
            ]),
            ("نيسان", "Nissan", 3, [
                ("التيما", "Altima", "2015-2026", "سيدان", "S,SV,SR,SL"),
                ("باترول", "Patrol", "2010-2026", "SUV", "XE,SE,LE,Platinum"),
                ("صني", "Sunny", "2015-2026", "سيدان", "S,SV"),
            ]),
            ("هيونداي", "Hyundai", 4, [
                ("النترا", "Elantra", "2016-2026", "سيدان", "Smart,Comfort,Premium"),
                ("توسان", "Tucson", "2016-2026", "SUV", "Smart,Comfort,Premium"),
                ("سوناتا", "Sonata", "2015-2026", "سيدان", "Smart,Premium"),
            ]),
            ("لكزس", "Lexus", 5, [
                ("ES", "ES", "2015-2026", "سيدان", "ES250,ES350,ES300h"),
                ("LX", "LX", "2015-2026", "SUV", "LX570,LX600"),
                ("RX", "RX", "2015-2026", "SUV", "RX350,RX450h"),
            ]),
            ("شيفروليه", "Chevrolet", 6, [
                ("تاهو", "Tahoe", "2015-2026", "SUV", "LS,LT,RST,Premier,High Country"),
                ("سلفرادو", "Silverado", "2019-2026", "بيك أب غمارة,بيك أب غمارتين", "WT,LT,RST,LTZ,High Country"),
            ]),
            ("فورد", "Ford", 7, [
                ("اكسبلورر", "Explorer", "2016-2026", "SUV", "Base,XLT,Limited,Platinum"),
                ("F-150", "F-150", "2015-2026", "بيك أب غمارة,بيك أب غمارتين", "XL,XLT,Lariat,King Ranch,Platinum"),
            ]),
            ("كيا", "Kia", 8, [
                ("سيراتو", "Cerato", "2015-2026", "سيدان", "LX,EX"),
                ("سبورتاج", "Sportage", "2016-2026", "SUV", "LX,EX,GT-Line"),
            ]),
        ]
        for bname, ben, sort, models in brands_data:
            c.execute("INSERT INTO vehicle_brands (name,name_en,sort) VALUES (?,?,?)", (bname, ben, sort))
            bid = c.lastrowid
            for mname, men, years, bodies, trims in models:
                c.execute("INSERT INTO vehicle_models (brand_id,name,name_en,years,bodies,trims) VALUES (?,?,?,?,?,?)",
                          (bid, mname, men, years, bodies, trims))

        c.execute("INSERT INTO users (phone,name,created_at) VALUES (?,?,?)",
                  ("0512345678", "عميل تجريبي", now()))
        uid = c.lastrowid
        c.execute("""INSERT INTO cars (user_id,brand,model,year,body,trim,engine,cylinders,fuel,transmission,color,is_default)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
                  (uid, "تويوتا", "كامري", "2020", "سيدان", "LE", "2.5L", "4", "بنزين", "أوتوماتيك", "أبيض"))
        c.execute("""INSERT INTO cars (user_id,brand,model,year,body,trim,engine,cylinders,fuel,transmission,color,is_default)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,0)""",
                  (uid, "جمس", "سييرا", "2023", "بيك أب غمارتين", "AT4", "5.3L", "8", "بنزين", "أوتوماتيك", "أسود"))
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
        self.send_header("Cache-Control", "no-store")
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
            return self._send_json(200, {"ok": True, "service": "turbas", "version": "3.0"})

        if path == "/api/delivery-zones":
            return self._send_json(200, [
                {"id": "sinaeya", "name": "صناعية العاصمة", "fee": 0},
                {"id": "nearby", "name": "أحياء قريبة من الصناعية", "fee": 25},
                {"id": "riyadh", "name": "باقي الرياض", "fee": 35},
            ])

        if path == "/api/home":
            return self._send_json(200, {"main": [
                {"id": "workshop", "name": "ورش", "icon": "🔧", "desc": "صيانة وإصلاح"},
                {"id": "parts", "name": "قطع غيار", "icon": "🔩", "desc": "قطع متوافقة"},
                {"id": "batteries", "name": "بطاريات", "icon": "🔋", "desc": "بطارية وتركيب"},
                {"id": "oils", "name": "زيوت", "icon": "🛢️", "desc": "زيت وفلتر"},
                {"id": "tires", "name": "كفرات", "icon": "🛞", "desc": "مقاس وتركيب"},
            ]})

        if path == "/api/categories":
            conn = get_db()
            parent = qs.get("parent_id", ["0"])[0]
            scope = qs.get("scope", ["workshop"])[0]
            data = j(conn.execute(
                "SELECT * FROM categories WHERE parent_id=? AND scope=? ORDER BY sort",
                (parent, scope)).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/services":
            conn = get_db()
            q = """SELECT sd.*, c.name as category_name, c.parent_id
                   FROM service_defs sd JOIN categories c ON c.id=sd.category_id WHERE 1=1"""
            params = []
            if "category_id" in qs:
                q += " AND sd.category_id=?"; params.append(qs["category_id"][0])
            q += " ORDER BY sd.sort, sd.id"
            data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/offers":
            conn = get_db()
            if "partner_id" in qs:
                data = j(conn.execute(
                    """SELECT o.*, sd.name as service_name FROM offers o
                       JOIN service_defs sd ON sd.id=o.service_def_id
                       WHERE o.partner_id=?""", (qs["partner_id"][0],)).fetchall())
            else:
                q = """SELECT o.id, o.service_def_id, o.price, o.duration, o.warranty_days,
                              o.includes, o.excludes,
                              p.turbas_rating, p.google_rating, p.jobs_count, p.warranty_ok, p.area,
                              sd.name as service_name, sd.description, sd.includes as def_includes, sd.excludes as def_excludes
                       FROM offers o
                       JOIN partners p ON p.id=o.partner_id
                       JOIN service_defs sd ON sd.id=o.service_def_id
                       WHERE o.active=1 AND p.active=1"""
                params = []
                if "service_def_id" in qs:
                    q += " AND o.service_def_id=?"; params.append(qs["service_def_id"][0])
                data = j(conn.execute(q, params).fetchall())
                def score(x):
                    return (x.get("turbas_rating") or 0) * 20 + (x.get("jobs_count") or 0) * 0.05 - (x.get("price") or 0) * 0.01
                data.sort(key=score, reverse=True)
            conn.close()
            return self._send_json(200, data)

        if path == "/api/products":
            conn = get_db()
            if "partner_id" in qs:
                data = j(conn.execute("SELECT * FROM products WHERE partner_id=?", (qs["partner_id"][0],)).fetchall())
            else:
                q = """SELECT pt.id, pt.partner_id, pt.kind, pt.name, pt.brand, pt.grade, pt.part_number,
                              pt.price, pt.warranty, pt.meta, pt.brands, pt.models, pt.years,
                              pt.width, pt.aspect, pt.rim, pt.viscosity, pt.volume, pt.cca, pt.size_code,
                              pt.stock, pt.delivery, p.area, p.turbas_rating
                       FROM products pt JOIN partners p ON p.id=pt.partner_id
                       WHERE pt.active=1"""
                params = []
                if "kind" in qs:
                    q += " AND pt.kind=?"; params.append(qs["kind"][0])
                if "brand" in qs and qs["brand"][0] not in ("", "الكل"):
                    q += " AND pt.brand=?"; params.append(qs["brand"][0])
                if "width" in qs:
                    q += " AND pt.width=?"; params.append(qs["width"][0])
                if "aspect" in qs:
                    q += " AND pt.aspect=?"; params.append(qs["aspect"][0])
                if "rim" in qs:
                    q += " AND pt.rim=?"; params.append(qs["rim"][0])
                data = j(conn.execute(q, params).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/vehicle/brands":
            conn = get_db()
            data = j(conn.execute("SELECT * FROM vehicle_brands ORDER BY sort, name").fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/vehicle/models":
            conn = get_db()
            bid = qs.get("brand_id", [None])[0]
            if not bid: return self._send_json(400, {"error": "brand_id"})
            data = j(conn.execute("SELECT * FROM vehicle_models WHERE brand_id=? ORDER BY name", (bid,)).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/vehicle/years":
            # expand years range string
            years = qs.get("years", [""])[0]
            out = []
            if "-" in years:
                a, b = years.split("-", 1)
                try:
                    out = list(range(int(a), int(b) + 1))
                except: out = []
            return self._send_json(200, out)

        if path == "/api/orders":
            conn = get_db()
            q = "SELECT * FROM orders WHERE 1=1"
            params = []
            if "user_id" in qs:
                q += " AND user_id=?"; params.append(qs["user_id"][0])
            if "partner_id" in qs:
                q += " AND partner_id=?"; params.append(qs["partner_id"][0])
            q += " ORDER BY id DESC"
            rows = j(conn.execute(q, params).fetchall())
            for r in rows:
                if r.get("reveal") or r.get("status") in ("paid", "confirmed", "in_progress", "done"):
                    p = conn.execute("SELECT name,area,phone,code FROM partners WHERE id=?", (r["partner_id"],)).fetchone()
                    if p:
                        r["partner_name"] = p["name"]; r["partner_area"] = p["area"]
                        r["partner_code"] = p["code"]
                        if r.get("reveal"): r["partner_phone"] = p["phone"]
                else:
                    r["partner_name"] = "مقدم خدمة"
            conn.close()
            return self._send_json(200, rows)

        m = re.match(r"^/api/orders/(\d+)$", path)
        if m:
            conn = get_db()
            r = conn.execute("SELECT * FROM orders WHERE id=?", (m.group(1),)).fetchone()
            if not r: conn.close(); return self._send_json(404, {"error": "not found"})
            r = dict(r)
            p = conn.execute("SELECT name,area,phone,code FROM partners WHERE id=?", (r["partner_id"],)).fetchone()
            if p and (r.get("reveal") or True):
                r["partner_name"] = p["name"]; r["partner_area"] = p["area"]; r["partner_code"] = p["code"]
                if r.get("reveal"): r["partner_phone"] = p["phone"]
            r["addons"] = j(conn.execute("SELECT * FROM order_addons WHERE order_id=?", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, r)

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM messages WHERE order_id=? ORDER BY id", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        if path == "/api/conversations":
            # list of chats for user or partner
            conn = get_db()
            if "user_id" in qs:
                rows = j(conn.execute("""SELECT o.id as order_id, o.title, o.status_text, o.price, o.car_info, o.created_at,
                    (SELECT body FROM messages WHERE order_id=o.id ORDER BY id DESC LIMIT 1) as last_msg,
                    (SELECT created_at FROM messages WHERE order_id=o.id ORDER BY id DESC LIMIT 1) as last_at
                    FROM orders o WHERE o.user_id=? ORDER BY o.id DESC""", (qs["user_id"][0],)).fetchall())
            elif "partner_id" in qs:
                rows = j(conn.execute("""SELECT o.id as order_id, o.title, o.status_text, o.price, o.car_info, o.created_at,
                    (SELECT body FROM messages WHERE order_id=o.id ORDER BY id DESC LIMIT 1) as last_msg,
                    (SELECT created_at FROM messages WHERE order_id=o.id ORDER BY id DESC LIMIT 1) as last_at
                    FROM orders o WHERE o.partner_id=? ORDER BY o.id DESC""", (qs["partner_id"][0],)).fetchall())
            else:
                rows = []
            conn.close()
            return self._send_json(200, rows)

        m = re.match(r"^/api/users/(\d+)/cars$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM cars WHERE user_id=? ORDER BY is_default DESC, id", (m.group(1),)).fetchall())
            conn.close()
            return self._send_json(200, data)

        m = re.match(r"^/api/cars/(\d+)/history$", path)
        if m:
            conn = get_db()
            data = j(conn.execute("SELECT * FROM service_history WHERE car_id=? ORDER BY id DESC", (m.group(1),)).fetchall())
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
            conn.close()
            return self._send_json(200, {
                "new": sum(1 for o in orders if o["status"] in ("paid", "new")),
                "confirmed": sum(1 for o in orders if o["status"] == "confirmed"),
                "in_progress": sum(1 for o in orders if o["status"] == "in_progress"),
                "done": sum(1 for o in orders if o["status"] == "done"),
                "sales": sales, "commission": commission, "net": round(sales - commission, 2),
            })

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
            conn.execute("""INSERT INTO cars (user_id,brand,model,year,body,trim,engine,cylinders,fuel,transmission,color,is_default)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (data["user_id"], data.get("brand"), data.get("model"), data.get("year"),
                          data.get("body"), data.get("trim"), data.get("engine"), data.get("cylinders"),
                          data.get("fuel"), data.get("transmission"), data.get("color"),
                          1 if data.get("is_default") else 0))
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
                (partner_id,kind,name,brand,grade,part_number,price,warranty,meta,brands,models,years,
                 width,aspect,rim,viscosity,volume,cca,size_code,stock,delivery,active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (data["partner_id"], data.get("kind") or "parts", data.get("name"),
                 data.get("brand") or "", data.get("grade") or "تجاري", data.get("part_number") or "",
                 data.get("price", 0), data.get("warranty") or "", data.get("meta") or "",
                 data.get("brands") or "", data.get("models") or "", data.get("years") or "",
                 data.get("width") or "", data.get("aspect") or "", data.get("rim") or "",
                 data.get("viscosity") or "", data.get("volume") or "", data.get("cca") or "",
                 data.get("size_code") or "", data.get("stock", 10), 1 if data.get("delivery", True) else 0))
            conn.commit()
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": pid})

        if path == "/api/orders":
            conn = get_db()
            partner_id = data.get("partner_id")
            offer_id = data.get("offer_id")
            if offer_id and not partner_id:
                off = conn.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
                if off:
                    partner_id = off["partner_id"]
                    data.setdefault("price", off["price"])
                    nm = conn.execute("SELECT name FROM service_defs WHERE id=?", (off["service_def_id"],)).fetchone()
                    if nm: data.setdefault("title", nm["name"])
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
            if partner_id:
                conn.execute("UPDATE partners SET jobs_count=jobs_count+1 WHERE id=?", (partner_id,))
                conn.commit()
            # service history if car_id provided
            if data.get("car_id"):
                p = conn.execute("SELECT name FROM partners WHERE id=?", (partner_id,)).fetchone()
                conn.execute("""INSERT INTO service_history (car_id,order_id,title,price,partner_name,done_at,notes)
                                VALUES (?,?,?,?,?,?,?)""",
                             (data["car_id"], oid, data.get("title"), data.get("price", 0),
                              p["name"] if p else "", now(), "طلب جديد"))
                conn.commit()
            p = conn.execute("SELECT name,area,phone,code FROM partners WHERE id=?", (partner_id,)).fetchone()
            conn.close()
            return self._send_json(201, {
                "id": oid, "points_earned": pts,
                "partner_name": p["name"] if p else None,
                "partner_area": p["area"] if p else None,
                "partner_phone": p["phone"] if p else None,
                "partner_code": p["code"] if p else None,
            })

        m = re.match(r"^/api/orders/(\d+)/status$", path)
        if m:
            oid = m.group(1)
            st = data.get("status") or "confirmed"
            text_map = {"paid": "تم الدفع", "confirmed": "مؤكد", "in_progress": "قيد التنفيذ",
                        "done": "مكتمل", "cancelled": "ملغي"}
            text = data.get("status_text") or text_map.get(st, st)
            conn = get_db()
            conn.execute("UPDATE orders SET status=?, status_text=?, reveal=1 WHERE id=?", (st, text, oid))
            conn.commit(); conn.close()
            return self._send_json(200, {"ok": True, "status": st, "status_text": text})

        m = re.match(r"^/api/orders/(\d+)/addons$", path)
        if m:
            conn = get_db()
            conn.execute("""INSERT INTO order_addons (order_id,title,price,reason,status,created_at)
                            VALUES (?,?,?,?,'pending',?)""",
                         (m.group(1), data.get("title"), data.get("price", 0), data.get("reason") or "", now()))
            conn.commit()
            aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.close()
            return self._send_json(201, {"id": aid})

        m = re.match(r"^/api/orders/(\d+)/addons/(\d+)$", path)
        if m:
            oid, aid = m.group(1), m.group(2)
            action = data.get("action")
            conn = get_db()
            if action == "accept":
                ad = conn.execute("SELECT * FROM order_addons WHERE id=?", (aid,)).fetchone()
                conn.execute("UPDATE order_addons SET status='accepted' WHERE id=?", (aid,))
                if ad: conn.execute("UPDATE orders SET price=price+? WHERE id=?", (ad["price"], oid))
                conn.commit()
            else:
                conn.execute("UPDATE order_addons SET status='rejected' WHERE id=?", (aid,))
                conn.commit()
            conn.close()
            return self._send_json(200, {"ok": True})

        m = re.match(r"^/api/orders/(\d+)/messages$", path)
        if m:
            conn = get_db()
            conn.execute("INSERT INTO messages (order_id,sender,body,msg_type,created_at) VALUES (?,?,?,?,?)",
                         (m.group(1), data.get("sender", "customer"), data.get("body", ""),
                          data.get("msg_type", "text"), now()))
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
    print("ترباس v3 → http://0.0.0.0:%d" % PORT)
    HTTPServer((HOST, PORT), App).serve_forever()
