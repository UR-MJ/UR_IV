# core/event_data_loader.py
"""
이벤트 데이터 로더 - variant_set 기반 시퀀스 검색
Step 0 = Parent (베이스), Step 1+ = Children (변형)

개선사항:
- 유사도 기반 프롬프트 검색 (Jaccard similarity)
- Children ID순 정렬 (스토리 순서 보장)
- 이전 스텝 기준 diff (스토리 진행감)
"""
import pandas as pd
from pathlib import Path


class EventDataLoader:
    """이벤트 데이터 로더 - variant_set 검색용"""

    REQUIRED_COLUMNS = [
        'id', 'parent_id', 'has_children', 'has_visible_children',
        'tag_string_general', 'tag_string_character',
        'tag_string_copyright', 'tag_string_artist', 'tag_string_meta',
        'rating', 'score', 'fav_count',
        'image_width', 'image_height',
    ]

    def __init__(self, parquet_dir: str = None):
        self.parquet_dir = parquet_dir
        self.df = None
        self.parents_df = None
        self.children_df = None
        self.parent_child_map = {}

    def load_parquets_by_rating(self, ratings: list = None, progress_callback=None):
        """Rating별 parquet 파일 로드 (고속 버전)"""
        if ratings is None:
            ratings = ['e']

        rating_files = {
            'g': 'danbooru_g.parquet',
            's': 'danbooru_s.parquet',
            'q': 'danbooru_q.parquet',
            'e': 'danbooru_e.parquet',
        }

        dfs = []
        total_before = 0
        total_after = 0

        for i, rating in enumerate(ratings):
            filename = rating_files.get(rating)
            if not filename:
                continue

            filepath = Path(self.parquet_dir) / filename
            if not filepath.exists():
                print(f"⚠️ {filename} 파일 없음")
                continue

            try:
                # ★ 필요한 컬럼만 읽기 (I/O 대폭 감소)
                df = pd.read_parquet(filepath, columns=self.REQUIRED_COLUMNS)

                total_before += len(df)

                # parent_id가 있거나 has_children인 것만 필터링
                mask = df['parent_id'].notna()
                if 'has_children' in df.columns:
                    mask = mask | (df['has_children'] == True)
                df = df[mask]

                total_after += len(df)

                # ★ 벡터화된 parent_id 정수 변환 (apply 대신)
                if 'parent_id' in df.columns:
                    df['parent_id'] = pd.to_numeric(df['parent_id'], errors='coerce').astype('Int64')

                if 'id' in df.columns:
                    df['id'] = df['id'].astype(int)

                dfs.append(df)
                print(f"✅ {filename}: {len(df)}개 로드")

                if progress_callback:
                    progress_callback(i + 1, len(ratings), filename)

            except Exception as e:
                # columns 파라미터 실패 시 폴백
                try:
                    df = pd.read_parquet(filepath)
                    available_cols = [c for c in self.REQUIRED_COLUMNS if c in df.columns]
                    df = df[available_cols]

                    total_before += len(df)
                    mask = df['parent_id'].notna()
                    if 'has_children' in df.columns:
                        mask = mask | (df['has_children'] == True)
                    df = df[mask]
                    total_after += len(df)

                    if 'parent_id' in df.columns:
                        df['parent_id'] = pd.to_numeric(df['parent_id'], errors='coerce').astype('Int64')
                    if 'id' in df.columns:
                        df['id'] = df['id'].astype(int)

                    dfs.append(df)
                    print(f"✅ {filename}: {len(df)}개 로드 (폴백)")
                    if progress_callback:
                        progress_callback(i + 1, len(ratings), filename)
                except Exception as e2:
                    print(f"⚠️ {filename} 로드 실패: {e2}")
                    import traceback
                    traceback.print_exc()

        if dfs:
            self.df = pd.concat(dfs, ignore_index=True)
            print(f"✅ 총 {len(self.df)}개 로드 (원본 {total_before}개 중)")
            self._build_parent_child_index()

        return self.df

    def _build_parent_child_index(self):
        """Parent-Child 인덱스 구축 (고속 버전)"""
        if self.df is None:
            return

        # Parent가 있는 이미지들 (Children)
        self.children_df = self.df[self.df['parent_id'].notna()].copy()
        print(f"✅ Children: {len(self.children_df)}개")

        # Parent ID 목록
        parent_ids = self.children_df['parent_id'].dropna().unique()

        # Parents (Children을 가진 이미지들) - set으로 빠른 lookup
        parent_id_set = set(parent_ids.astype(int))
        self.parents_df = self.df[self.df['id'].isin(parent_id_set)].copy()
        print(f"✅ Parents: {len(self.parents_df)}개")

        # ★ Parent -> Children 매핑 생성 (groupby로 고속화)
        grouped = self.children_df.groupby('parent_id')['id'].apply(list)
        self.parent_child_map = {int(k): v for k, v in grouped.items()}

        # ★ Parents에 미리 태그 세트를 캐싱 (유사도 검색 고속화)
        if 'tag_string_general' in self.parents_df.columns:
            self.parents_df['_tag_set'] = self.parents_df['tag_string_general'].apply(
                lambda x: set(
                    t.strip().lower().replace('_', ' ')
                    for t in str(x).split() if t.strip()
                ) if pd.notna(x) else set()
            )

        print(f"✅ Parent-Child 매핑: {len(self.parent_child_map)}개 그룹")

    # ──────────────────────────────────────────────────────
    #  A. 유사도 기반 프롬프트 검색 (신규)
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_tags(text: str) -> set:
        """쉼표/공백 구분 태그 문자열을 정규화된 set으로 변환"""
        if not text:
            return set()
        # 쉼표로 먼저 분리, 없으면 공백
        if ',' in text:
            parts = text.split(',')
        else:
            parts = text.split()
        return set(
            t.strip().lower().replace('_', ' ')
            for t in parts if t.strip()
        )

    @staticmethod
    def _jaccard(set_a: set, set_b: set) -> float:
        """Jaccard 유사도 (0.0 ~ 1.0)"""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _overlap_ratio(query: set, target: set) -> float:
        """쿼리 태그 중 target에 포함된 비율 (0.0 ~ 1.0), 부분 문자열 매칭 지원"""
        if not query:
            return 0.0
        matched = 0
        for q_tag in query:
            # 정확히 일치하면 바로 카운트
            if q_tag in target:
                matched += 1
            else:
                # 부분 문자열 매칭 (boy -> 2boys, 3boys 등)
                for t_tag in target:
                    if q_tag in t_tag:
                        matched += 1
                        break
        return matched / len(query)

    @staticmethod
    def _jaccard_fuzzy(query: set, target: set) -> float:
        """부분 문자열 매칭을 포함한 Jaccard 유사도"""
        if not query or not target:
            return 0.0
        matched_target = set()
        for q_tag in query:
            if q_tag in target:
                matched_target.add(q_tag)
            else:
                for t_tag in target:
                    if q_tag in t_tag:
                        matched_target.add(t_tag)
                        break
        intersection = len(matched_target)
        union = len(query | target)
        return intersection / union if union > 0 else 0.0

    def search_by_prompt(
        self,
        prompt: str,
        exclude_tags: str = "",
        child_include: str = "",
        child_exclude: str = "",
        min_children: int = 2,
        max_children: int = 20,
        min_score: int = 0,
        require_variant_set: bool = False,
        limit: int = 100,
    ) -> list:
        """
        ★ 프롬프트 기반 유사도 검색 (핵심 개선)

        입력 프롬프트의 태그와 Parent 태그의 유사도를 계산하여
        가장 근접한 이벤트를 랭킹하여 반환합니다.

        유사도 = 0.6 * overlap_ratio + 0.4 * jaccard
        (overlap_ratio: 내 태그가 얼마나 포함되었는지 중시)
        """
        if self.parents_df is None or len(self.parents_df) == 0:
            return []

        query_tags = self._parse_tags(prompt)
        exclude_set = self._parse_tags(exclude_tags)
        child_inc_set = self._parse_tags(child_include)
        child_exc_set = self._parse_tags(child_exclude)

        if not query_tags:
            return []

        filtered = self.parents_df.copy()

        # variant_set 필터
        if require_variant_set and 'tag_string_meta' in filtered.columns:
            filtered = filtered[
                filtered['tag_string_meta'].str.contains(
                    'variant_set|large_variant_set', na=False, regex=True
                )
            ]

        # 점수 필터
        if min_score > 0 and 'score' in filtered.columns:
            filtered = filtered[filtered['score'] >= min_score]

        # 제외 태그 사전 필터 (빠른 필터링)
        if exclude_set:
            for tag in exclude_set:
                tag_u = tag.replace(' ', '_')
                tag_s = tag.replace('_', ' ')
                mask = ~(
                    filtered['tag_string_general'].str.lower().str.contains(tag_u, na=False) |
                    filtered['tag_string_general'].str.lower().str.contains(tag_s, na=False)
                )
                filtered = filtered[mask]

        print(f"🔍 사전 필터링 후 Parent 후보: {len(filtered)}개")

        # ★ 유사도 계산
        scored_results = []

        for _, parent in filtered.iterrows():
            parent_id = int(parent['id'])
            if parent_id not in self.parent_child_map:
                continue

            parent_tag_set = parent.get('_tag_set', set())
            if not parent_tag_set:
                parent_tag_set = self._parse_tags(parent.get('tag_string_general', ''))

            # 유사도 계산 (부분 문자열 매칭 포함)
            overlap = self._overlap_ratio(query_tags, parent_tag_set)
            jaccard = self._jaccard_fuzzy(query_tags, parent_tag_set)
            similarity = 0.6 * overlap + 0.4 * jaccard

            # 최소 1개 태그는 일치해야 함
            if overlap == 0:
                continue

            # Children 확인
            child_ids = self.parent_child_map[parent_id]
            children = self.children_df[self.children_df['id'].isin(child_ids)].copy()

            if len(children) < min_children or len(children) > max_children:
                continue

            # Child 포함 조건 (부분 문자열 매칭 지원)
            if child_inc_set:
                all_child_tags = set()
                for _, c in children.iterrows():
                    all_child_tags.update(self._parse_tags(c.get('tag_string_general', '')))
                # 정확 매칭 또는 부분 문자열 매칭
                found_any = False
                for inc_tag in child_inc_set:
                    if inc_tag in all_child_tags:
                        found_any = True
                        break
                    for ct in all_child_tags:
                        if inc_tag in ct:
                            found_any = True
                            break
                    if found_any:
                        break
                if not found_any:
                    continue

            # Child 제외 조건
            if child_exc_set:
                for tag in child_exc_set:
                    tag_u = tag.replace(' ', '_')
                    tag_s = tag.replace('_', ' ')
                    mask = ~(
                        children['tag_string_general'].str.lower().str.contains(tag_u, na=False) |
                        children['tag_string_general'].str.lower().str.contains(tag_s, na=False)
                    )
                    children = children[mask]
                if len(children) < min_children:
                    continue

            # ★ Children을 ID순 정렬 (스토리 순서)
            children = children.sort_values('id', ascending=True)

            # 부분 문자열 포함 매칭 카운트
            matched_count = 0
            for q_tag in query_tags:
                if q_tag in parent_tag_set:
                    matched_count += 1
                else:
                    for t_tag in parent_tag_set:
                        if q_tag in t_tag:
                            matched_count += 1
                            break

            scored_results.append({
                'parent': parent.to_dict(),
                'children': children.to_dict('records'),
                'child_count': len(children),
                'similarity': round(similarity, 3),
                'matched_tags': matched_count,
                'total_query_tags': len(query_tags),
            })

        # ★ 유사도 내림차순 정렬, 같으면 score 내림차순
        scored_results.sort(
            key=lambda x: (x['similarity'], x['parent'].get('score', 0)),
            reverse=True
        )

        print(f"✅ 유사도 검색 결과: {len(scored_results)}개 (상위 {limit}개 반환)")
        return scored_results[:limit]

    # ──────────────────────────────────────────────────────
    #  기존 search_events (하위 호환용 유지)
    # ──────────────────────────────────────────────────────

    def search_events(
        self,
        parent_include: str = "",
        parent_exclude: str = "",
        child_include: str = "",
        child_exclude: str = "",
        min_children: int = 2,
        max_children: int = 20,
        min_score: int = 0,
        ratings: list = None,
        require_variant_set: bool = False,
        limit: int = 100
    ):
        """기존 이벤트 검색 (하위 호환)"""
        if self.parents_df is None or len(self.parents_df) == 0:
            print("⚠️ Parent 데이터가 없습니다.")
            return []

        results = []
        filtered_parents = self.parents_df.copy()

        if require_variant_set and 'tag_string_meta' in filtered_parents.columns:
            filtered_parents = filtered_parents[
                filtered_parents['tag_string_meta'].str.contains(
                    'variant_set|large_variant_set', na=False, regex=True
                )
            ]

        if ratings and 'rating' in filtered_parents.columns:
            filtered_parents = filtered_parents[filtered_parents['rating'].isin(ratings)]

        if min_score > 0 and 'score' in filtered_parents.columns:
            filtered_parents = filtered_parents[filtered_parents['score'] >= min_score]

        if parent_include:
            include_tags = [t.strip().lower() for t in parent_include.split(',') if t.strip()]
            for tag in include_tags:
                tag_underscore = tag.replace(' ', '_')
                tag_space = tag.replace('_', ' ')
                mask = (
                    filtered_parents['tag_string_general'].str.lower().str.contains(tag_underscore, na=False) |
                    filtered_parents['tag_string_general'].str.lower().str.contains(tag_space, na=False)
                )
                filtered_parents = filtered_parents[mask]

        if parent_exclude:
            exclude_tags = [t.strip().lower() for t in parent_exclude.split(',') if t.strip()]
            for tag in exclude_tags:
                tag_underscore = tag.replace(' ', '_')
                tag_space = tag.replace('_', ' ')
                mask = ~(
                    filtered_parents['tag_string_general'].str.lower().str.contains(tag_underscore, na=False) |
                    filtered_parents['tag_string_general'].str.lower().str.contains(tag_space, na=False)
                )
                filtered_parents = filtered_parents[mask]

        if 'score' in filtered_parents.columns:
            filtered_parents = filtered_parents.sort_values('score', ascending=False)

        for _, parent in filtered_parents.iterrows():
            if len(results) >= limit:
                break

            parent_id = int(parent['id'])
            if parent_id not in self.parent_child_map:
                continue

            child_ids = self.parent_child_map[parent_id]
            children = self.children_df[self.children_df['id'].isin(child_ids)].copy()

            if len(children) < min_children or len(children) > max_children:
                continue

            if child_include:
                include_tags = [t.strip().lower() for t in child_include.split(',') if t.strip()]
                has_required = False
                for tag in include_tags:
                    tag_underscore = tag.replace(' ', '_')
                    tag_space = tag.replace('_', ' ')
                    if (
                        children['tag_string_general'].str.lower().str.contains(tag_underscore, na=False).any() or
                        children['tag_string_general'].str.lower().str.contains(tag_space, na=False).any()
                    ):
                        has_required = True
                        break
                if not has_required:
                    continue

            if child_exclude:
                exclude_tags = [t.strip().lower() for t in child_exclude.split(',') if t.strip()]
                for tag in exclude_tags:
                    tag_underscore = tag.replace(' ', '_')
                    tag_space = tag.replace('_', ' ')
                    mask = ~(
                        children['tag_string_general'].str.lower().str.contains(tag_underscore, na=False) |
                        children['tag_string_general'].str.lower().str.contains(tag_space, na=False)
                    )
                    children = children[mask]

            if len(children) < min_children:
                continue

            # ★ Children ID순 정렬 (C. 스토리 순서 보장)
            children = children.sort_values('id', ascending=True)

            results.append({
                'parent': parent.to_dict(),
                'children': children.to_dict('records'),
                'child_count': len(children),
            })

        return results

    # ──────────────────────────────────────────────────────
    #  B. 이전 스텝 기준 diff로 build_steps 개선
    # ──────────────────────────────────────────────────────

    def build_steps(self, event: dict) -> list:
        """
        이벤트를 스텝 리스트로 변환
        ★ 개선: Children을 ID순 정렬 + 이전 스텝 기준 diff

        Step 0 = Parent (베이스)
        Step 1+ = Children (변형, ID순 = 스토리 순)
        """
        parent = event['parent']
        children = event['children']

        # ★ C. Children을 ID순 정렬 (스토리 순서 보장)
        children = sorted(children, key=lambda c: c.get('id', 0))

        # Parent 태그
        parent_tags = self._parse_tags(parent.get('tag_string_general', ''))

        steps = []

        # Step 0: Parent (베이스)
        steps.append({
            'step': 0,
            'id': parent.get('id'),
            'is_parent': True,
            'tags': parent_tags.copy(),
            'tags_str': ', '.join(sorted(parent_tags)),
            'character': parent.get('tag_string_character', ''),
            'copyright': parent.get('tag_string_copyright', ''),
            'artist': parent.get('tag_string_artist', ''),
            'rating': parent.get('rating', ''),
            'score': parent.get('score', 0),
            'added': [],
            'removed': [],
            'added_from_parent': [],
            'removed_from_parent': [],
        })

        # Step 1+: Children
        prev_tags = parent_tags.copy()

        for i, child in enumerate(children):
            child_tags = self._parse_tags(child.get('tag_string_general', ''))

            # ★ B. 이전 스텝 기준 diff (스토리 진행감)
            added_from_prev = sorted(child_tags - prev_tags)
            removed_from_prev = sorted(prev_tags - child_tags)

            # Parent 기준 diff도 보조로 유지
            added_from_parent = sorted(child_tags - parent_tags)
            removed_from_parent = sorted(parent_tags - child_tags)

            steps.append({
                'step': i + 1,
                'id': child.get('id'),
                'is_parent': False,
                'tags': child_tags.copy(),
                'tags_str': ', '.join(sorted(child_tags)),
                'character': child.get('tag_string_character', ''),
                'copyright': child.get('tag_string_copyright', ''),
                'artist': child.get('tag_string_artist', ''),
                'rating': child.get('rating', ''),
                'score': child.get('score', 0),
                'added': added_from_prev,
                'removed': removed_from_prev,
                'added_from_parent': added_from_parent,
                'removed_from_parent': removed_from_parent,
            })

            prev_tags = child_tags.copy()

        return steps

    def get_event_summary(self, event: dict) -> str:
        """이벤트 요약 문자열 생성"""
        parent = event['parent']
        child_count = event['child_count']

        parent_id = parent.get('id', 'N/A')
        score = parent.get('score', 0)
        rating = parent.get('rating', '?')
        similarity = event.get('similarity', None)
        matched = event.get('matched_tags', None)
        total_q = event.get('total_query_tags', None)

        tags = parent.get('tag_string_general', '').split()[:5]
        tags_preview = ', '.join(t.replace('_', ' ') for t in tags)

        # ★ 유사도 정보 포함
        sim_str = ""
        if similarity is not None:
            pct = int(similarity * 100)
            sim_str = f" | 유사도:{pct}% ({matched}/{total_q})"

        return (
            f"[{rating.upper()}] score:{score} | "
            f"{child_count} steps{sim_str} | "
            f"{tags_preview}..."
        )
