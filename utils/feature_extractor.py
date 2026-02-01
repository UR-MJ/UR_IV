# utils/feature_extractor.py
"""
프롬프트에서 캐릭터 특징 추출
tags_db의 parquet 파일 활용
"""
import os
from pathlib import Path
from typing import List, Set, Optional


class FeatureExtractor:
    """캐릭터 특징 추출기 (tags_db 활용)"""
    
    PERSON_COUNTS = {
        '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls',
        '1boy', '2boys', '3boys', '4boys', '5boys', '6+boys',
        '1other', '2others', '3others', '4others', '5others', '6+others',
    }
    
    def __init__(self, tags_db_path: str = None):
        self.tags_db_path = Path(tags_db_path) if tags_db_path else self._find_tags_db_path()
        
        # 색상 목록 (color.txt에서 로드)
        self.colors: Set[str] = set()
        
        # 카테고리별 태그
        self.hair_colors: Set[str] = set()
        self.hair_styles: Set[str] = set()
        self.eye_colors: Set[str] = set()
        self.special_features: Set[str] = set()
        self.all_characteristics: Set[str] = set()
        
        # 로드
        self._load_colors()
        self._load_characteristics()
        self._load_parquet_files()
        self._generate_color_combinations()
    
    def _find_tags_db_path(self) -> Path:
        """tags_db 경로 찾기"""
        candidates = [
            Path(__file__).parent.parent / "tags_db",
            Path("tags_db"),
            Path("../tags_db"),
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        return Path("tags_db")
    
    def _load_colors(self):
        """color.txt에서 색상 로드"""
        color_file = self.tags_db_path / "color.txt"
        
        if not color_file.exists():
            print(f"⚠️ color.txt not found: {color_file}")
            # 기본 색상
            self.colors = {
                'red', 'blue', 'green', 'yellow', 'purple', 'pink',
                'orange', 'white', 'black', 'brown', 'grey', 'gray',
                'silver', 'gold', 'golden', 'aqua', 'blonde', 'platinum',
                'light blue', 'dark blue', 'light brown', 'dark brown',
            }
            return
        
        try:
            with open(color_file, 'r', encoding='utf-8') as f:
                for line in f:
                    color = line.strip().lower()
                    if color:
                        self.colors.add(color)
            print(f"✅ color.txt: {len(self.colors)}개 색상 로드")
        except Exception as e:
            print(f"❌ color.txt 로드 실패: {e}")
    
    def _load_characteristics(self):
        """characteristic_list.txt 로드"""
        char_file = self.tags_db_path / "characteristic_list.txt"
        
        if not char_file.exists():
            print(f"⚠️ characteristic_list.txt not found")
            return
        
        try:
            with open(char_file, 'r', encoding='utf-8') as f:
                for line in f:
                    tag = line.strip().lower()
                    if tag:
                        self.all_characteristics.add(tag)
            print(f"✅ characteristic_list.txt: {len(self.all_characteristics)}개 로드")
        except Exception as e:
            print(f"❌ characteristic_list.txt 로드 실패: {e}")
    
    def _load_parquet_files(self):
        """parquet 파일들 로드"""
        try:
            import pandas as pd
        except ImportError:
            print("⚠️ pandas가 없어 parquet 로드 불가")
            return
        
        # 로드할 파일 매핑
        file_mapping = {
            'hair_styles': ['hair_styles.parquet', 'hair.parquet'],
            'hair_color': ['hair_color.parquet'],
            'eye_tags': ['eyes_tags.parquet'],
            'special': [
                'ears_tags.parquet', 'tail.parquet', 'wings.parquet',
                'body_parts.parquet',
            ],
            # colors.parquet는 제외 (배경/테마용)
        }
        
        for category, filenames in file_mapping.items():
            for filename in filenames:
                file_path = self.tags_db_path / filename
                if file_path.exists():
                    try:
                        df = pd.read_parquet(file_path)
                        tags = self._extract_tags_from_df(df)
                        
                        if category == 'hair_styles':
                            self.hair_styles.update(tags)
                        elif category == 'hair_color':
                            self.hair_colors.update(tags)
                        elif category == 'eye_tags':
                            # eyes_tags에서 색 관련만 추출
                            for tag in tags:
                                if 'eyes' in tag:
                                    self.eye_colors.add(tag)
                        elif category == 'special':
                            self.special_features.update(tags)
                        
                        self.all_characteristics.update(tags)
                    except Exception as e:
                        print(f"⚠️ {filename} 로드 실패: {e}")
        
        print(f"✅ parquet 로드 완료 - "
              f"머리스타일: {len(self.hair_styles)}, "
              f"눈: {len(self.eye_colors)}, "
              f"특수: {len(self.special_features)}")
              
    def _extract_tags_from_df(self, df) -> Set[str]:
        """DataFrame에서 태그 추출"""
        tags = set()
        tag_columns = ['tag', 'tags', 'name', 'Tag', 'Name', 'tag_name']
        
        for col in tag_columns:
            if col in df.columns:
                values = df[col].dropna().astype(str).str.lower().tolist()
                tags.update(values)
                break
        
        return tags
    
    def _generate_color_combinations(self):
        """색상 + hair/eyes 조합 생성"""
        for color in self.colors:
            hair_tag = f"{color} hair"
            self.hair_colors.add(hair_tag)
            self.all_characteristics.add(hair_tag)
            
            eyes_tag = f"{color} eyes"
            self.eye_colors.add(eyes_tag)
            self.all_characteristics.add(eyes_tag)
        
        print(f"✅ 색상 조합 생성 - 머리색: {len(self.hair_colors)}, 눈색: {len(self.eye_colors)}")
    
    def extract_features(self, prompt: str, max_count: int = 3) -> List[str]:
        """프롬프트에서 특징 추출"""
        if not prompt:
            return []
        
        tags = [t.strip().lower() for t in prompt.split(',')]
        found = []
        
        for category_set in [self.hair_colors, self.eye_colors, 
                             self.hair_styles, self.special_features]:
            for tag in tags:
                if tag in category_set and tag not in found:
                    found.append(tag)
                    if len(found) >= max_count:
                        return found
        
        if len(found) < max_count:
            for tag in tags:
                if tag in self.all_characteristics and tag not in found:
                    found.append(tag)
                    if len(found) >= max_count:
                        return found
        
        return found
    
    def extract_person_count(self, prompt: str) -> List[str]:
        """인물 수 태그 추출"""
        if not prompt:
            return []
        
        tags = [t.strip().lower() for t in prompt.split(',')]
        return [tag for tag in tags if tag in self.PERSON_COUNTS]
    
    def get_display_name(self, character: str, prompt: str) -> str:
        """표시용 이름 반환"""
        if character and character.lower() != 'nan' and character.strip():
            chars = [c.strip() for c in character.split(',')]
            name = chars[0].replace('_', ' ')
            return name[:23] + '...' if len(name) > 25 else name
        
        features = self.extract_features(prompt, max_count=3)
        return '\n'.join(features) if features else '(no info)'
    
    def is_characteristic(self, tag: str) -> bool:
        """태그가 캐릭터 특징인지 확인"""
        return tag.lower() in self.all_characteristics


# ========== 싱글톤 및 헬퍼 함수 ==========

_extractor_instance = None


def get_feature_extractor() -> FeatureExtractor:
    """싱글톤 인스턴스 반환"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = FeatureExtractor()
    return _extractor_instance              