import sqlite3, sys, json
# Label / CNF-derived iron & calcium for the household staples the auto-fill skipped.
# Values are per the row's basis (100g rows: per 100 g; serving rows: per serving). Sources noted.
VALS = {
 # (iron_mg, calcium_mg, source note)
 'astro_original':  (0.0, 108.7, 'label: Ca 125 mg & iron 0 per 115 g -> per 100 g'),
 'on_isolate_scoop':(0.0, 140.0, 'label per 30 g scoop: Ca 140 mg; iron not listed (~0)'),
 'egg_whites_liquid':(0.08, 7.0, 'CNF egg white raw (~0.08 mg Fe, 7 mg Ca /100 g)'),
 'roti':            (3.9, 34.0, 'atta per USDA 20080 (Fe 3.6-3.9, Ca 34 /100 g flour) x 25 g/35 g cooked -> per 100 g roti ~2.8 Fe, 24 Ca'),
 'paneer':          (0.2, 480.0, 'typical full-fat paneer (IFCT 2017 ~480 mg Ca, 0.2 mg Fe /100 g)'),
 'peanuts_salted':  (2.26, 54.0, 'USDA FDC dry-roasted salted peanuts'),
 'chai':            (0.02, 80.0, 'unsweetened, ~67 g 2% milk/cup (CNF 61: Ca 120 mg/100 g)'),
 'dal_katori':      (2.3, 30.0, '~33 g dry toor/masoor (CNF lentils raw ~7 mg Fe, ~ 90 mg Ca /100 g dry) + tadka'),
 'sabzi_katori':    (1.0, 45.0, 'mixed-veg estimate (CNF veg avg ~0.6 Fe, ~30 Ca /100 g) + oil'),
}
# roti: apply the conversion described (flour share of cooked weight)
VALS['roti'] = (round(3.9 * 25 / 35, 2), round(34 * 25 / 35, 1), VALS['roti'][2])
db = sys.argv[1]
c = sqlite3.connect(db)
for k, (fe, ca, src) in VALS.items():
    r = c.execute("SELECT basis, iron_mg, calcium_mg, notes FROM foods WHERE key=?", (k,)).fetchone()
    if not r:
        print('missing', k); continue
    if r[1] is not None or r[2] is not None:
        print('kept', k, r[1], r[2]); continue
    note = (r[3] + ' | ' if r[3] else '') + f'minerals 2026-10-13: {src}'
    c.execute("UPDATE foods SET iron_mg=?, calcium_mg=?, notes=?, updated_at=datetime('now') WHERE key=?", (fe, ca, note, k))
    print('set', k, fe, ca, r[0])
c.commit()
