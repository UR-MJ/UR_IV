# core/database.py
import sqlite3
from pathlib import Path

def normalize_path(path):
    """경로 정규화"""
    return Path(path).resolve().as_posix()

class MetadataManager:
    """이미지 메타데이터 관리 클래스"""

    _ALLOWED_TOGGLE_FIELDS = {'is_favorite', 'pending_command', 'pending_delete'}

    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()

    def close(self):
        """DB 연결 종료"""
        if self.conn:
            self.conn.close()
            self.conn = None

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
            # 마이그레이션: image_hash 컬럼 추가
            try:
                self.conn.execute(
                    "ALTER TABLE images ADD COLUMN image_hash TEXT DEFAULT ''"
                )
            except Exception:
                pass  # 이미 존재하면 무시
    
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
        if field not in self._ALLOWED_TOGGLE_FIELDS:
            raise ValueError(f"허용되지 않는 필드: {field}")
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

    def update_image_hash(self, path: str, hash_val: str):
        """이미지 해시 업데이트"""
        with self.conn:
            self.conn.execute(
                "UPDATE images SET image_hash=? WHERE path=?",
                (hash_val, path)
            )

    def find_duplicates_in_folder(self, folder_path: str) -> list:
        """폴더 내 중복 이미지 그룹 반환 [(hash, [paths...])]"""
        cur = self.conn.cursor()
        query_path = folder_path.rstrip('/') + '/'
        cur.execute(
            "SELECT image_hash, GROUP_CONCAT(path, '|||') FROM images "
            "WHERE path LIKE ? AND image_hash != '' AND image_hash IS NOT NULL "
            "GROUP BY image_hash HAVING COUNT(*) > 1",
            (query_path + '%',)
        )
        result = []
        for row in cur.fetchall():
            hash_val = row[0]
            paths = row[1].split('|||')
            result.append((hash_val, paths))
        return result

    def get_all_exif_in_folder(self, folder_path: str) -> list:
        """폴더 내 모든 (path, exif) 반환"""
        cur = self.conn.cursor()
        query_path = folder_path.rstrip('/') + '/'
        cur.execute(
            "SELECT path, exif FROM images WHERE path LIKE ? AND exif IS NOT NULL AND exif != ''",
            (query_path + '%',)
        )
        return cur.fetchall()

    def update_path(self, old_path: str, new_path: str) -> None:
        """이미지 경로(PK) 변경"""
        old_norm = normalize_path(old_path)
        new_norm = normalize_path(new_path)
        with self.conn:
            self.conn.execute(
                "UPDATE images SET path=? WHERE path=?",
                (new_norm, old_norm)
            )

    def search_exif(self, keywords: list, folder_path: str) -> list:
        """키워드 AND 검색 (폴더 범위)"""
        cur = self.conn.cursor()
        query = "SELECT path FROM images WHERE path LIKE ? AND "
        params = [folder_path.rstrip('/') + '/' + '%'] + [f'%{kw}%' for kw in keywords]
        conditions = " AND ".join(["exif LIKE ?"] * len(keywords))
        query += conditions
        cur.execute(query, params)
        return [row[0] for row in cur.fetchall()]