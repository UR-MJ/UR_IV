# utils/file_wildcard.py
"""
파일 기반 와일드카드 시스템
- 문법: ~/이름/~ → wildcards/이름.txt 에서 랜덤 선택
- 문법: ~/이름:n/~ → n개 그룹에서 각각 1개씩 뽑기
- 각 줄이 하나의 그룹, 쉼표로 구분된 옵션 중 하나를 랜덤 선택
- 중첩 와일드카드 지원: 와일드카드 내에서 다른 ~/이름/~ 참조
- [A|B] 문법 지원 (OR 선택)
"""
import os
import re
import random
from typing import Dict, List, Optional, Tuple

# 와일드카드 패턴: ~/이름/~ 또는 ~/이름:n/~
FILE_WILDCARD_PATTERN = re.compile(r'~/([^/]+?)/~')
# OR 선택 패턴: [A|B|C]
OR_PATTERN = re.compile(r'\[([^\[\]]+?\|[^\[\]]+?)\]')


class FileWildcardManager:
    """파일 기반 와일드카드 관리자 (싱글톤)"""

    def __init__(self, wildcards_dir: str = None):
        if wildcards_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            wildcards_dir = os.path.join(base, 'wildcards')
        self.wildcards_dir = wildcards_dir
        os.makedirs(self.wildcards_dir, exist_ok=True)
        self._cache: Dict[str, List[List[str]]] = {}
        self._cache_mtime: Dict[str, float] = {}

    def reload(self):
        """캐시 초기화 (파일 변경 후 호출)"""
        self._cache.clear()
        self._cache_mtime.clear()

    def get_wildcard_names(self) -> List[str]:
        """사용 가능한 와일드카드 이름 목록 반환"""
        names = []
        if not os.path.isdir(self.wildcards_dir):
            return names
        for f in sorted(os.listdir(self.wildcards_dir)):
            if f.endswith('.txt'):
                names.append(f[:-4])
        return names

    def load_wildcard(self, name: str) -> List[List[str]]:
        """
        와일드카드 파일 로드 (캐시 사용)
        반환: [[옵션1, 옵션2, ...], [옵션A, 옵션B, ...], ...]
              각 리스트가 하나의 '그룹' (파일의 한 줄)
        """
        filepath = os.path.join(self.wildcards_dir, f'{name}.txt')
        if not os.path.isfile(filepath):
            return []

        # 캐시 유효성 검사
        mtime = os.path.getmtime(filepath)
        if name in self._cache and self._cache_mtime.get(name) == mtime:
            return self._cache[name]

        groups = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # 쉼표로 옵션 분리
                options = [opt.strip() for opt in line.split(',') if opt.strip()]
                if options:
                    groups.append(options)

        self._cache[name] = groups
        self._cache_mtime[name] = mtime
        return groups

    def save_wildcard(self, name: str, content: str):
        """와일드카드 파일 저장"""
        filepath = os.path.join(self.wildcards_dir, f'{name}.txt')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        # 캐시 무효화
        self._cache.pop(name, None)
        self._cache_mtime.pop(name, None)

    def delete_wildcard(self, name: str):
        """와일드카드 파일 삭제"""
        filepath = os.path.join(self.wildcards_dir, f'{name}.txt')
        if os.path.isfile(filepath):
            os.remove(filepath)
        self._cache.pop(name, None)
        self._cache_mtime.pop(name, None)

    def get_wildcard_content(self, name: str) -> str:
        """와일드카드 파일 내용 반환 (편집용)"""
        filepath = os.path.join(self.wildcards_dir, f'{name}.txt')
        if not os.path.isfile(filepath):
            return ''
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()

    def resolve(self, text: str, max_depth: int = 10) -> str:
        """
        텍스트 내의 모든 ~/이름/~ 와일드카드를 치환
        - ~/이름/~ : 모든 그룹에서 각각 1개씩 선택, 쉼표로 연결
        - ~/이름:n/~ : n개 그룹만 랜덤 선택하여 각각 1개씩
        - 중첩 지원 (max_depth까지 반복)
        """
        if not text:
            return text

        depth = 0
        prev = None
        while prev != text and depth < max_depth:
            prev = text
            text = FILE_WILDCARD_PATTERN.sub(self._replace_match, text)
            depth += 1

        # [A|B] OR 패턴 처리
        text = self._resolve_or_patterns(text)

        return text

    def _replace_match(self, match) -> str:
        """단일 와일드카드 매치 교체"""
        raw = match.group(1)

        # n-pick 파싱: 이름:n
        if ':' in raw:
            parts = raw.rsplit(':', 1)
            name = parts[0].strip()
            try:
                n_pick = int(parts[1].strip())
            except ValueError:
                name = raw
                n_pick = 0  # 0 = 전체
        else:
            name = raw.strip()
            n_pick = 0

        groups = self.load_wildcard(name)
        if not groups:
            return match.group(0)  # 파일이 없으면 원본 유지

        # 그룹 선택
        if n_pick > 0 and n_pick < len(groups):
            selected_groups = random.sample(groups, n_pick)
        else:
            selected_groups = groups

        # 각 그룹에서 하나씩 선택
        picked = []
        for group in selected_groups:
            choice = random.choice(group)
            # [A|B] 패턴이 있으면 처리
            choice = self._resolve_or_patterns(choice)
            picked.append(choice.strip())

        return ', '.join(picked)

    def _resolve_or_patterns(self, text: str) -> str:
        """[A|B|C] 패턴을 랜덤 선택으로 교체"""
        def _replace_or(m):
            options = [o.strip() for o in m.group(1).split('|') if o.strip()]
            return random.choice(options) if options else ''

        prev = None
        while prev != text:
            prev = text
            text = OR_PATTERN.sub(_replace_or, text)
        return text

    def preview(self, name: str) -> str:
        """와일드카드 미리보기 (한 번 실행 결과)"""
        groups = self.load_wildcard(name)
        if not groups:
            return '(파일 없음)'
        picked = []
        for group in groups:
            choice = random.choice(group)
            choice = self._resolve_or_patterns(choice)
            picked.append(choice.strip())
        return ', '.join(picked)

    def get_info(self, name: str) -> dict:
        """와일드카드 정보 반환"""
        groups = self.load_wildcard(name)
        total_options = sum(len(g) for g in groups)
        return {
            'name': name,
            'groups': len(groups),
            'total_options': total_options,
        }


# 싱글톤
_instance: Optional[FileWildcardManager] = None


def get_file_wildcard_manager() -> FileWildcardManager:
    global _instance
    if _instance is None:
        _instance = FileWildcardManager()
    return _instance


def resolve_file_wildcards(text: str) -> str:
    """간편 함수: 파일 와일드카드 치환"""
    return get_file_wildcard_manager().resolve(text)
