import sqlite3

DB = "forum_data.db"

def main():
    print("=" * 50)
    print("БАЗА ДАННЫХ")
    print("=" * 50)
    
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM complaints")
    print(f"\nВсего: {c.fetchone()[0]}")
    
    c.execute("SELECT server, COUNT(*) FROM complaints GROUP BY server")
    print("\nПо серверам:")
    for s, n in c.fetchall():
        print(f"   {s}: {n}")
    
    c.execute("SELECT section, COUNT(*) FROM complaints GROUP BY section ORDER BY COUNT(*) DESC")
    print("\nПо разделам:")
    for s, n in c.fetchall():
        print(f"   {s}: {n}")
    
    print("\nПоследние 10:")
    print("-" * 50)
    c.execute("SELECT title, author_nick, author_static, violator_nick, violator_static FROM complaints ORDER BY parsed_at DESC LIMIT 10")
    for i, (t, an, ast, vn, vst) in enumerate(c.fetchall(), 1):
        print(f"\n{i}. {t}\n   {an} ({ast}) -> {vn} ({vst})")
    
    print("\n" + "=" * 50)
    q = input("\nПоиск (Enter - выход): ").strip()
    if q:
        c.execute("SELECT title, author_nick, author_static, violator_nick, violator_static, url FROM complaints WHERE author_nick LIKE ? OR violator_nick LIKE ? OR author_static LIKE ? OR violator_static LIKE ? OR raw_content LIKE ? LIMIT 20",
            (f"%{q}%",) * 5)
        rows = c.fetchall()
        print(f"\nНайдено: {len(rows)}")
        for i, (t, an, ast, vn, vst, u) in enumerate(rows, 1):
            print(f"\n{i}. {t}\n   {an} ({ast}) -> {vn} ({vst})\n   {u}")
    conn.close()

if __name__ == "__main__":
    main()
    input("\nEnter...")
