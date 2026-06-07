from ea_db_repository import BaseRepository
from eparser import EParser
import sqlite3

class SQLiteRepository(BaseRepository):
    def __init__(self, db_path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.ConnectionString = db_path

    def _execute(self, query: str, params: tuple = ()) -> list:
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

class E17Parser(EParser):
    def connect(self, filename: str) -> BaseRepository:
        self.repository = SQLiteRepository(filename)
        return self.repository