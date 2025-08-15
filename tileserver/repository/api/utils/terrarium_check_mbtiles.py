import sqlite3
from pathlib import Path

mbtiles_path = Path("/ix1/whcdh/data/terrarium/tiles/terrarium.mbtiles")

conn = sqlite3.connect(mbtiles_path)
cur = conn.cursor()

print(f"{'Zoom':<5} {'Actual':>12} {'Expected':>12} {'% Complete':>12}")
print("-" * 45)

for z in range(0, 13):  # 0–12
    cur.execute("SELECT COUNT(*) FROM tiles WHERE zoom_level=?", (z,))
    actual = cur.fetchone()[0]
    expected = 4 ** z
    pct = (actual / expected * 100) if expected > 0 else 100
    print(f"{z:<5} {actual:>12,} {expected:>12,} {pct:>11.2f}%")

conn.close()
