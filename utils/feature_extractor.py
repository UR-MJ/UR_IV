# utils/feature_extractor.py
"""
프롬프트에서 캐릭터 특징 추출.
TagDatabase의 통합 그룹 카탈로그와 선별 용어를 활용한다.
"""
from pathlib import Path
from typing import List, Set

from core.tag_database import TagAsset, TagDatabase, get_tag_database


class FeatureExtractor:
    """캐릭터 특징 추출기 (tags_db 활용)"""
    
    PERSON_COUNTS = {
        '1girl', '2girls', '3girls', '4girls', '5girls', '6+girls',
        '1boy', '2boys', '3boys', '4boys', '5boys', '6+boys',
        '1other', '2others', '3others', '4others', '5others', '6+others',
    }
    
    def __init__(self, tags_db_path: str = None):
        self.database = TagDatabase(Path(tags_db_path)) if tags_db_path else get_tag_database()
        self.tags_db_path = self.database.root
        
        # 수동 선별 색상 목록
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
    
    def _load_colors(self):
        """수동 선별 색상 용어를 로드."""
        color_file = self.database.path(TagAsset.COLOR_TERMS_CURATED)
        
        if not color_file.exists():
            print(f"[FeatureExtractor] curated color terms not found: {color_file}")
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
            print(f"[FeatureExtractor] curated color terms loaded: {len(self.colors)}")
        except Exception as e:
            print(f"[FeatureExtractor] curated color term load failed: {e}")
    
    def _load_characteristics(self):
        """수동 선별 외형 태그를 로드."""
        char_file = self.database.path(TagAsset.APPEARANCE_TAGS_CURATED)
        
        if not char_file.exists():
            print("[FeatureExtractor] curated appearance tags not found")
            return
        
        try:
            with open(char_file, 'r', encoding='utf-8') as f:
                for line in f:
                    tag = line.strip().lower()
                    if tag:
                        self.all_characteristics.add(tag)
            print(
                f"[FeatureExtractor] curated appearance tags loaded: "
                f"{len(self.all_characteristics)}"
            )
        except Exception as e:
            print(f"[FeatureExtractor] curated appearance tag load failed: {e}")
    
    def _load_parquet_files(self):
        """통합 Wiki 그룹 카탈로그에서 외형 관련 그룹을 로드."""
        try:
            groups = self.database.load_tag_groups()
        except Exception as e:
            print(f"[FeatureExtractor] tag group load failed: {e}")
            return

        self.hair_styles.update(groups.get("hair_styles", set()))
        self.hair_styles.update(groups.get("hair", set()))
        self.hair_colors.update(groups.get("hair_color", set()))
        self.eye_colors.update(
            tag for tag in groups.get("eyes_tags", set()) if "eyes" in tag
        )
        for group_name in ("ears_tags", "tail", "wings", "body_parts"):
            self.special_features.update(groups.get(group_name, set()))

        self.all_characteristics.update(self.hair_styles)
        self.all_characteristics.update(self.hair_colors)
        self.all_characteristics.update(self.eye_colors)
        self.all_characteristics.update(self.special_features)

        print(
            f"[FeatureExtractor] groups loaded: hair_styles={len(self.hair_styles)}, "
            f"eyes={len(self.eye_colors)}, special={len(self.special_features)}"
        )
              
    def _generate_color_combinations(self):
        """색상 + hair/eyes 조합 생성"""
        for color in self.colors:
            hair_tag = f"{color} hair"
            self.hair_colors.add(hair_tag)
            self.all_characteristics.add(hair_tag)
            
            eyes_tag = f"{color} eyes"
            self.eye_colors.add(eyes_tag)
            self.all_characteristics.add(eyes_tag)
        
        print(
            f"[FeatureExtractor] color combinations: hair={len(self.hair_colors)}, "
            f"eyes={len(self.eye_colors)}"
        )
    
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
