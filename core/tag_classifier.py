# core/tag_classifier.py
"""
태그 분류 및 필터링 유틸리티
"""
import os
import re
import pandas as pd
from pathlib import Path

TAGS_DB_PATH = Path(__file__).parent.parent / "tags_db"


class TagClassifier:
    def __init__(self):
        # 기본 태그 세트
        self.characters = set()
        self.copyrights = set()
        self.artists = set()
        self.clothes = set()
        self.characteristics = set()
        self.colors = set()
        
        # Wiki 그룹
        self.wiki_groups = {}
        self.tag_to_category = {}
        
        # 특수 태그
        self.censorship_tags = set()
        self.text_tags = set()
        
        # 경로 설정
        self.tags_db_dir = str(TAGS_DB_PATH)
        
        # 로드
        self._load_all_python_dicts()
        self._load_text_files()
        self._load_wiki_groups()
        self._load_special_tags()
    
    def _load_all_python_dicts(self):
        """딕셔너리 파일에서 태그 로드"""
        # 캐릭터: character_dictionary.py 또는 danbooru_character.py
        for name in ["character_dictionary.py", "danbooru_character.py"]:
            char_path = TAGS_DB_PATH / name
            if char_path.exists():
                self.characters = self._load_python_dict_keys(char_path)
                print(f"✅ 캐릭터: {name} → {len(self.characters)}개 로드")
                break

        # 작품: copyright_dictionary.py 또는 copyright_list_reformatted.py
        for name in ["copyright_dictionary.py", "copyright_list_reformatted.py"]:
            copy_path = TAGS_DB_PATH / name
            if copy_path.exists():
                self.copyrights = self._load_python_dict_keys(copy_path)
                print(f"✅ 작품: {name} → {len(self.copyrights)}개 로드")
                break

        # 작가: artist_dictionary.py
        artist_path = TAGS_DB_PATH / "artist_dictionary.py"
        if artist_path.exists():
            self.artists = self._load_python_dict_keys(artist_path)
            print(f"✅ 작가: artist_dictionary.py → {len(self.artists)}개 로드")

    def _load_python_dict_keys(self, filepath):
        """Python 파일에서 dict 키 또는 list 항목을 로드"""
        tags = set()
        try:
            namespace = {}
            with open(filepath, 'r', encoding='utf-8') as f:
                exec(f.read(), namespace)

            # namespace에서 dict/list 찾기
            for key, val in namespace.items():
                if key.startswith('_'):
                    continue
                if isinstance(val, dict):
                    for k in val.keys():
                        tag = str(k).lower().strip()
                        if tag:
                            tags.add(tag)
                    break
                elif isinstance(val, (list, tuple)):
                    for item in val:
                        tag = str(item).lower().strip()
                        if tag:
                            tags.add(tag)
                    break
        except Exception as e:
            print(f"⚠️ {filepath} 로드 실패: {e}")

        return tags
    
    def _load_text_files(self):
        """텍스트 파일 로드"""
        clothes_path = TAGS_DB_PATH / "clothes_list.txt"
        if clothes_path.exists():
            self.clothes = self._load_text_file(clothes_path)
        
        char_path = TAGS_DB_PATH / "characteristic_list.txt"
        if char_path.exists():
            self.characteristics = self._load_text_file(char_path)
        
        color_path = TAGS_DB_PATH / "color.txt"
        if color_path.exists():
            self.colors = self._load_text_file(color_path)
    
    def _load_text_file(self, filepath):
        """텍스트 파일에서 라인별로 로드"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [line.strip().lower() for line in f if line.strip()]
            return set(lines)
        except Exception as e:
            print(f"⚠️ 파일 로드 실패 {filepath}: {e}")
            return set()
    
    def _load_special_tags(self):
        """검열/텍스트 태그 로드"""
        # censorship
        censor_path = TAGS_DB_PATH / "censorship.parquet"
        if censor_path.exists():
            try:
                df = pd.read_parquet(censor_path)
                if 'name' in df.columns:
                    self.censorship_tags = set(df['name'].str.lower().tolist())
                elif 'tag' in df.columns:
                    self.censorship_tags = set(df['tag'].str.lower().tolist())
                elif len(df.columns) > 0:
                    self.censorship_tags = set(str(t).lower() for t in df.iloc[:, 0] if pd.notna(t))
            except Exception as e:
                print(f"⚠️ censorship.parquet 로드 실패: {e}")
        
        # 기본 검열 태그 추가
        default_censorship = {
            'censored', 'mosaic censoring', 'bar censoring', 
            'blur censor', 'light censoring', 'novelty censoring',
            'heart censor', 'steam censor', 'convenient censoring',
            'censored nipples', 'censored pussy', 'censored penis',
            'mosaic_censoring', 'bar_censoring', 'light_censoring'
        }
        self.censorship_tags.update(default_censorship)
        print(f"✅ censorship 태그: {len(self.censorship_tags)}개 로드")
        
        # text
        text_path = TAGS_DB_PATH / "text.parquet"
        if text_path.exists():
            try:
                df = pd.read_parquet(text_path)
                if 'name' in df.columns:
                    self.text_tags = set(df['name'].str.lower().tolist())
                elif 'tag' in df.columns:
                    self.text_tags = set(df['tag'].str.lower().tolist())
                elif len(df.columns) > 0:
                    self.text_tags = set(str(t).lower() for t in df.iloc[:, 0] if pd.notna(t))
            except Exception as e:
                print(f"⚠️ text.parquet 로드 실패: {e}")
        print(f"✅ text 태그: {len(self.text_tags)}개 로드")
    
    def _load_wiki_groups(self):
        """Wiki tag groups 로드"""
        if not os.path.exists(self.tags_db_dir):
            print(f"⚠️ tags_db 폴더 없음: {self.tags_db_dir}")
            return
        
        category_mapping = {
            "body_parts": ["body_parts", "ass", "breasts_tags", "hair", "hair_color", 
                          "hair_styles", "eyes_tags", "face_tags", "ears_tags", 
                          "hands", "legs", "feet", "shoulders", "neck_and_neckwear",
                          "skin_color", "skin_folds", "bra"],
            "clothing": ["clothes_list", "dress", "attire", "shirt", "pants", 
                        "legwear", "sleeves", "headwear", "eyewear", "handwear",
                        "covering", "fashion_style", "patterns", "embellishment",
                        "panties", "sexual_attire"],
            "pose": ["posture", "gestures", "sexual_positions", "dances"],
            "expression": ["face_tags"],
            "composition": ["focus_tags", "image_composition", "scan"],
            "background": ["backgrounds", "locations", "real_world_locations",
                          "holidays_and_celebrations", "history"],
            "effect": ["lighting", "censorship", "metatags", "visual_novel_games",
                      "water", "fire", "flowers", "symbols"],
            "objects": ["audio_tags", "food_tags", "weapons", "technology",
                       "video_game", "board_games", "fighting_games", 
                       "platform_games", "role-playing_games", "shooter_games",
                       "text", "prints", "tail", "wings"],
            "character_trait": ["characteristic_list", "family_relationships", "groups",
                               "jobs", "legendary_creatures", "people", "companies_and_brand_names"],
            "animals": ["birds", "cats", "dogs"],
            "art_style": ["fine_art_parody", "drawing_software", "japanese_dialects",
                         "artistic_license", "phrases"],
            "sexual": ["sex_acts", "sex_objects", "nudity", "pussy",
                      "sexual_attire", "sexual_positions", "simulated_sex_acts"],
            "color": ["colors", "hair_color", "skin_color"]
        }
        
        mixed_files = {
            "ass": ["body_parts", "pose", "composition"],
            "breasts_tags": ["body_parts", "pose"],
            "pussy": ["body_parts", "sexual"],
            "metatags": ["effect", "composition"],
        }
        
        try:
            parquet_files = [f for f in os.listdir(self.tags_db_dir) if f.endswith('.parquet')]
        except Exception as e:
            print(f"⚠️ 폴더 읽기 실패: {e}")
            return
        
        print(f"📦 Wiki groups 로드 중... ({len(parquet_files)}개 파일)")
        
        for filename in parquet_files:
            filepath = os.path.join(self.tags_db_dir, filename)
            group_name = filename.replace('.parquet', '')
            
            try:
                df = pd.read_parquet(filepath)
                
                if 'tag' in df.columns:
                    tags = df['tag'].tolist()
                elif 'name' in df.columns:
                    tags = df['name'].tolist()
                elif len(df.columns) > 0:
                    tags = df.iloc[:, 0].tolist()
                else:
                    continue
                
                self.wiki_groups[group_name] = set(str(t).lower() for t in tags if pd.notna(t))
                
                if group_name in mixed_files:
                    categories = mixed_files[group_name]
                else:
                    categories = [self._find_category(group_name, category_mapping)]
                
                for tag in self.wiki_groups[group_name]:
                    if tag not in self.tag_to_category:
                        self.tag_to_category[tag] = []
                    for cat in categories:
                        self.tag_to_category[tag].append({'group': group_name, 'category': cat})
                
            except Exception as e:
                print(f"⚠️ 파일 로드 실패 {filename}: {e}")
        
        print(f"✅ {len(self.wiki_groups)}개 그룹, {len(self.tag_to_category)}개 태그 로드 완료")
    
    def _find_category(self, group_name, category_mapping):
        """그룹명을 카테고리로 매핑"""
        group_lower = group_name.lower()
        for category, keywords in category_mapping.items():
            if group_lower in keywords:
                return category
        return "general"
    
    def filter_tags(self, tags_list, remove_censorship=False, remove_text=False):
        """태그 필터링"""
        result = []
        for tag in tags_list:
            tag_lower = tag.lower()
            if remove_censorship and tag_lower in self.censorship_tags:
                continue
            if remove_text and tag_lower in self.text_tags:
                continue
            result.append(tag)
        return result
    
    def is_censorship_tag(self, tag):
        """검열 관련 태그인지 확인"""
        tag_lower = tag.lower().strip()
        
        # 직접 매칭
        if tag_lower in self.censorship_tags:
            return True
        
        # 띄어쓰기 <-> 언더스코어 변환 매칭
        tag_underscore = tag_lower.replace(' ', '_')
        tag_space = tag_lower.replace('_', ' ')
        
        if tag_underscore in self.censorship_tags:
            return True
        if tag_space in self.censorship_tags:
            return True
        
        return False


    def is_text_tag(self, tag):
        """텍스트 태그인지 확인"""
        tag_lower = tag.lower().strip()
        
        # 직접 매칭
        if tag_lower in self.text_tags:
            return True
        
        # 띄어쓰기 <-> 언더스코어 변환 매칭
        tag_underscore = tag_lower.replace(' ', '_')
        tag_space = tag_lower.replace('_', ' ')
        
        if tag_underscore in self.text_tags:
            return True
        if tag_space in self.text_tags:
            return True
        
        return False
        
    def _tag_variants(self, tag: str) -> list:
        """태그의 모든 변형 생성 (공백/언더스코어, 이스케이프 괄호)"""
        tag_clean = tag.strip().lower()
        variants = {tag_clean}
        variants.add(tag_clean.replace('_', ' '))
        variants.add(tag_clean.replace(' ', '_'))
        variants.add(tag_clean.replace(r'\(', '(').replace(r'\)', ')'))
        variants.add(tag_clean.replace('(', r'\(').replace(')', r'\)'))
        # 언더스코어→공백 + 이스케이프 해제 조합
        tag_space = tag_clean.replace('_', ' ')
        variants.add(tag_space.replace(r'\(', '(').replace(r'\)', ')'))
        return list(variants)

    def classify_tag(self, tag):
        """태그 분류"""
        variants = self._tag_variants(tag)

        if any(v in self.characters for v in variants):
            return "character"
        if any(v in self.copyrights for v in variants):
            return "copyright"
        if any(v in self.artists for v in variants):
            return "artist"
        
        if tag_clean in self.tag_to_category:
            groups_info = self.tag_to_category[tag_clean]
            all_categories = [info['category'] for info in groups_info]
            priority = ["sexual", "body_parts", "clothing", "pose", "expression",
                       "character_trait", "composition", "background", "effect",
                       "objects", "animals", "art_style", "color"]
            for cat in priority:
                if cat in all_categories:
                    return cat
            return all_categories[0] if all_categories else "general"
        
        if tag_clean in self.clothes:
            return "clothing"
        if tag_clean in self.characteristics:
            return "character_trait"
        
        words = tag_clean.split()
        if any(word in self.colors for word in words):
            return "color"
        
        return "general"
    
    def classify_tags_for_event(self, tags_list):
        """이벤트 생성용 특화 분류"""
        classified = {
            "count": [], "character": [], "copyright": [], "costume": [],
            "appearance": [], "expression": [], "action": [], "background": [],
            "composition": [], "effect": [], "objects": [], "general": []
        }
        
        count_tags = {
            "1boy", "2boys", "3boys", "4boys", "5boys", "6+boys", 
            "1girl", "2girls", "3girls", "4girls", "5girls", "6+girls",
            "1other", "2others", "3others", "4others", "5others", "6+others"
        }
        
        for tag in tags_list:
            tag_lower = tag.lower()
            if tag_lower in count_tags:
                classified["count"].append(tag)
                continue
            
            category = self.classify_tag(tag)
            mapping = {
                "character": "character", "copyright": "copyright",
                "clothing": "costume", "body_parts": "appearance",
                "expression": "expression", "pose": "action",
                "background": "background", "composition": "composition",
                "effect": "effect", "objects": "objects"
            }
            key = mapping.get(category, "general")
            classified[key].append(tag)
        
        return classified