from database.connection import get_connection


class PersistentMemory:

    def save(self, key, value):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO memories(key, value)
            VALUES (?, ?)
            """,
            (key, value)
        )

        conn.commit()
        conn.close()

    def load(self, key):

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT value FROM memories
            WHERE key = ?
            """,
            (key,)
        )

        row = cursor.fetchone()

        conn.close()

        if row:
            return row[0]

        return None
    def delete(self, key):

        conn = get_connection()

        cursor = conn.cursor()

        cursor.execute(
        """
            DELETE FROM memories
            WHERE key = ?
            """,
            (key,)
        )

        conn.commit()

        conn.close()