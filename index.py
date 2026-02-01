import json
import sqlite3
import os
import re
from tqdm import tqdm # 진행 상황을 보여주는 라이브러리 (pip install tqdm)

SOURCE_JSONL_FILE = 'dantags_and_prompts_fix.jsonl'
DB_FILE = 'prompts_fts.sqlite' # 생성될 DB 파일 이름
TABLE_NAME = 'prompts'

def create_fts_database():
    """
    jsonl 파일을 읽어 FTS5 데이터베이스를 생성합니다.
    이 스크립트는 'blue hair' 같은 다중 단어 태그가 분리되지 않도록 처리합니다.
    """
    if os.path.exists(DB_FILE):
        print(f"'{DB_FILE}'이 이미 존재합니다. 새로 생성하려면 기존 파일을 삭제하고 다시 실행해주세요.")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # FTS5 가상 테이블 생성
    # ✅ 수정된 부분: 등호(=)를 제거하여 오래된 SQLite 버전과의 호환성을 높였습니다.
    print("FTS5 테이블 생성 중...")
    cur.execute(f"""
        CREATE VIRTUAL TABLE {TABLE_NAME} USING fts5(
            all_tags,
            json_bundle,
            tokenize 'unicode61' 'tokenchars=_'
        );
    """)

    print(f"'{SOURCE_JSONL_FILE}' 파일을 읽어 데이터베이스를 구축합니다...")

    try:
        total_lines = sum(1 for line in open(SOURCE_JSONL_FILE, 'r', encoding='utf-8'))

        with open(SOURCE_JSONL_FILE, 'r', encoding='utf-8') as f:
            cur.execute("BEGIN TRANSACTION")
            
            for line in tqdm(f, total=total_lines, desc="DB 생성 중"):
                try:
                    bundle = json.loads(line)
                    all_tags_set = set()
                    for category in ['general', 'character', 'copyright', 'artist']:
                        tag_string = bundle.get(category, '')
                        if tag_string:
                            # 태그 내 공백을 '_'로 치환하여 하나의 토큰으로 만듭니다.
                            tags_in_category = {tag.strip().replace(" ", "_") for tag in re.split(r',\s*', tag_string) if tag.strip()}
                            all_tags_set.update(tags_in_category)
                    
                    all_tags_text = ' '.join(all_tags_set)
                    json_bundle_text = json.dumps(bundle)

                    cur.execute(f"INSERT INTO {TABLE_NAME} (all_tags, json_bundle) VALUES (?, ?)", (all_tags_text, json_bundle_text))

                except (json.JSONDecodeError, AttributeError):
                    continue
            
            cur.execute("COMMIT")

    except FileNotFoundError:
        print(f"오류: '{SOURCE_JSONL_FILE}' 파일을 찾을 수 없습니다.")
        conn.close()
        return
    except Exception as e:
        print(f"데이터베이스 생성 중 오류 발생: {e}")
        cur.execute("ROLLBACK")
        conn.close()
        return

    print("데이터베이스 인덱싱 및 최적화 중...")
    cur.execute(f"INSERT INTO {TABLE_NAME}({TABLE_NAME}) VALUES('optimize');")
    
    conn.commit()
    conn.close()

    print(f"\n✅ FTS5 데이터베이스 생성이 성공적으로 완료되었습니다!")

if __name__ == '__main__':
    # tqdm 라이브러리가 없다면 설치해주세요. (pip install tqdm)
    create_fts_database()
