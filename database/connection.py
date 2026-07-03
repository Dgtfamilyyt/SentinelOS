import sqlite3

DATABASE = "database/memory.db"


def get_connection():
    return sqlite3.connect(DATABASE)