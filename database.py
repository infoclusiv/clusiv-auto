import sqlite3

from config import DATABASE_FILE


def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS channels 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      channel_id TEXT UNIQUE NOT NULL, 
                      channel_name TEXT NOT NULL, 
                      category TEXT DEFAULT 'Noticias')"""
    )
    conn.commit()
    conn.close()


def obtener_canales_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id, channel_name, category FROM channels ORDER BY category"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def agregar_canal_db(ch_id, ch_name):
    conn = sqlite3.connect(DATABASE_FILE)
    try:
        conn.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES (?, ?)",
            (ch_id.strip(), ch_name.strip()),
        )
        conn.commit()
        return True, f"Canal '{ch_name}' guardado."
    except sqlite3.IntegrityError:
        return False, "El ID del canal ya existe."
    finally:
        conn.close()


def eliminar_canal_db(ch_id):
    conn = sqlite3.connect(DATABASE_FILE)
    conn.execute("DELETE FROM channels WHERE channel_id = ?", (ch_id,))
    conn.commit()
    conn.close()