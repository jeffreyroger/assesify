import sqlite3

def ensure_column(db_path, table, column, col_def):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table});")
    cols = [r[1] for r in c.fetchall()]
    print('existing columns in',table,':', cols)
    if column not in cols:
        print(f"Adding {column} to {table}")
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def};")
        conn.commit()
    else:
        print(f"{column} already present in {table}")
    conn.close()

if __name__ == '__main__':
    db = 'assesify_dev.db'
    ensure_column(db, 'lessons', 'teacher_id', 'INTEGER')
