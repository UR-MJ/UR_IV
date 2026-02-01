# core/database.py
import sqlite3
from pathlib import Path

def normalize_path(path):
    """경로 정규화"""
    return Path(path).resolve().as_posix()

class MetadataManager:
    """이미지 메타데이터 관리 클래스"""
    
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    path TEXT PRIMARY KEY,
                    exif TEXT,
                    is_favorite INTEGER DEFAULT 0,
                    pending_command INTEGER DEFAULT 0,
                    pending_delete INTEGER DEFAULT 0
                )
            """)
    
    def get_image_data(self, path):
        if not path: 
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT exif, is_favorite, pending_command, pending_delete FROM images WHERE path=?", 
            (normalize_path(path),)
        )
        return cur.fetchone()

    def toggle_status(self, path, field):
        norm_path = normalize_path(path)
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO images (path) VALUES (?)", (norm_path,))
            self.conn.execute(f"UPDATE images SET {field} = 1 - {field} WHERE path=?", (norm_path,))
        self.conn.commit()

    def get_all_favorites(self):
        """모든 즐겨찾기 이미지 경로 반환"""
        cur = self.conn.cursor()
        cur.execute("SELECT path FROM images WHERE is_favorite = 1")
        return [row[0] for row in cur.fetchall()]

    def add_or_update_exif(self, path: str, exif: str) -> None:
        """EXIF 정보 삽입 또는 업데이트"""
        with self.conn:
            self.conn.execute("""
                INSERT INTO images (path, exif) VALUES (?, ?)
                ON CONFLICT(path) DO UPDATE SET exif=excluded.exif
            """, (path, exif))

    def get_all_paths_in_folder(self, folder_path: str) -> list:
        """폴더 내 모든 이미지 경로 반환"""
        cur = self.conn.cursor()
        query_path = folder_path.rstrip('/') + '/'
        cur.execute("SELECT path FROM images WHERE path LIKE ?", (query_path + '%',))
        return [row[0] for row in cur.fetchall()]

    def search_exif(self, keywords: list, folder_path: str) -> list:
        """키워드 AND 검색 (폴더 범위)"""
        cur = self.conn.cursor()
        query = "SELECT path FROM images WHERE path LIKE ? AND "
        params = [folder_path.rstrip('/') + '/' + '%'] + [f'%{kw}%' for kw in keywords]
        conditions = " AND ".join(["exif LIKE ?"] * len(keywords))
        query += conditions
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]