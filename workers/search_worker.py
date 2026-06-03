# workers/search_worker.py
import os
import re
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

class PandasSearchWorker(QThread):
    """Pandas를 이용한 검색 워커"""
    results_ready = pyqtSignal(list, int)
    status_update = pyqtSignal(str)

    # 검색에 필요한 컬럼만 로드 (메모리 절약)
    REQUIRED_COLUMNS = ['copyright', 'character', 'artist', 'general', 'meta']

    cached_df = None
    cached_col_lower = {}  # {col_name: lowercase Series} — rating/year 변경 시 무효화
    loaded_ratings = set()
    loaded_year = ''       # 현재 캐시에 로드된 년도 ('2025' | '2026' | '')

    # 사용 가능한 년도 — danbooru_optimized/ 에서 자동 감지 가능하지만 단순화 위해 고정
    AVAILABLE_YEARS = ('2026', '2025')
    DEFAULT_YEAR = '2026'

    def __init__(self, parquet_dir, selected_ratings, queries, exclude_queries=None,
                 combine_mode: str = 'and', dataset_year: str = None):
        """
        :param queries: { col: 'pattern' } 포함 검색 — 필드 간 결합은 combine_mode로 제어
        :param exclude_queries: { col: 'pattern' } 제외 검색 — 모드와 무관하게
            언제나 AND-NOT (제외는 "이건 절대 안 됨"의 의미라 OR 모드여도 항상 제외 적용)
        :param combine_mode: 'and' (교집합) | 'or' (합집합) — 필드 간 결합 방식
        :param dataset_year: '2026' (기본) | '2025' — 데이터셋 년도 선택
            2026은 2025를 포함하는 확장판이므로 둘을 동시 선택할 필요 없음
        """
        super().__init__()
        self.parquet_dir = parquet_dir
        self.selected_ratings = set(selected_ratings)
        self.queries = queries
        self.exclude_queries = exclude_queries or {}
        self.combine_mode = (combine_mode or 'and').lower()
        if self.combine_mode not in ('and', 'or'):
            self.combine_mode = 'and'
        # 년도 검증 — 허용 목록에 없으면 기본값으로
        self.dataset_year = str(dataset_year or self.DEFAULT_YEAR)
        if self.dataset_year not in self.AVAILABLE_YEARS:
            self.dataset_year = self.DEFAULT_YEAR
        self.is_running = True

    def run(self):
        """검색 실행"""
        try:
            if not self._load_data():
                return

            if self.cached_df is None or self.cached_df.empty:
                self.results_ready.emit([], 0)
                return

            self.status_update.emit(
                f"🔍 데이터 검색 중 (모드: {self.combine_mode.upper()})..."
            )
            print(f"[Search] === START === year={self.dataset_year} ratings={sorted(self.selected_ratings)} mode={self.combine_mode}")

            df = self.cached_df
            print(f"[Search] cached_df shape: {df.shape}")

            # ── 포함 검색 — 필드 간 결합은 combine_mode에 따라 ──
            non_empty_fields = [
                (col, txt) for col, txt in self.queries.items()
                if txt and col in df.columns
            ]
            print(f"[Search] non_empty_fields: {[(c, t[:50]) for c, t in non_empty_fields]}")

            n_total = len(df)

            def _wc_note(n: int) -> str:
                """매칭 수가 전체와 같으면 wildcard(필드 면제) 발동 표시"""
                return ' [WILDCARD — 필드 면제]' if n == n_total else ''

            if not non_empty_fields:
                total_mask = pd.Series(True, index=df.index)
                print(f"[Search] no fields → all rows pass ({n_total:,})")
            elif self.combine_mode == 'or':
                # OR: 빈 마스크에서 시작해 |= 누적
                total_mask = pd.Series(False, index=df.index)
                for col, search_text in non_empty_fields:
                    cm = self._parse_condition(df, col, search_text)
                    n_match = int(cm.sum())
                    print(f"[Search] OR  | {col:>10s} '{search_text[:60]}...' → {n_match:,} matches{_wc_note(n_match)}")
                    total_mask |= cm
            else:
                # AND: True에서 시작해 &= 누적
                total_mask = pd.Series(True, index=df.index)
                for col, search_text in non_empty_fields:
                    cm = self._parse_condition(df, col, search_text)
                    n_match = int(cm.sum())
                    print(f"[Search] AND | {col:>10s} '{search_text[:60]}...' → {n_match:,} matches{_wc_note(n_match)}")
                    total_mask &= cm
                    print(f"[Search]     ↳ cumulative AND mask: {int(total_mask.sum()):,}")

            # ── 제외 검색 — 모드와 무관하게 항상 AND-NOT ──
            for col, search_text in self.exclude_queries.items():
                if not search_text:
                    continue
                if col not in df.columns:
                    continue
                exclude_mask = self._parse_condition(df, col, search_text)
                n_excl = int(exclude_mask.sum())
                print(f"[Search] EXC | {col:>10s} '{search_text[:60]}...' → {n_excl:,} excluded")
                total_mask &= ~exclude_mask

            # 결과 필터링
            filtered_df = df[total_mask]
            total_count = len(filtered_df)
            print(f"[Search] === DONE === final mask: {int(total_mask.sum()):,} → emitting {total_count:,} rows")

            final_df = filtered_df.fillna("")
            results = final_df.to_dict('records')

            self.results_ready.emit(results, total_count)
            self.status_update.emit(
                f"✅ {self.combine_mode.upper()} 검색 완료: {total_count:,}건"
            )

        except Exception as e:
            self.status_update.emit(f"❌ 오류 발생: {str(e)}")
            self.results_ready.emit([], 0)

    def _parse_condition(self, df, col, query_text):
        """통합 태그 매칭 엔진 — 와일드카드 + 그룹 + OR/AND 지원
        combine_mode를 tag_matcher에 전달:
        - 'and': 콤마=AND (기존)
        - 'or':  콤마=OR (필드 내 콤마도 OR로 결합)
        명시적 [A|B], [A,B] 그룹은 모드와 무관하게 항상 OR/AND.

        성능: col_lower 캐시 사용 — 같은 rating set 내에서 lowercase 재사용.
        쿼리 1회당 ~수백ms (5M rows) 절약.
        """
        from core.tag_matcher import filter_dataframe
        col_lower = self._get_col_lower(df, col)
        return filter_dataframe(df, col, query_text,
                                default_combine=self.combine_mode,
                                col_lower=col_lower)

    @classmethod
    def _get_col_lower(cls, df, col: str):
        """lowercase Series 캐시 — 같은 rating set 내에서 재사용.
        cached_df가 바뀌면 _load_data에서 cache가 clear됨.
        """
        if col in cls.cached_col_lower:
            return cls.cached_col_lower[col]
        if col not in df.columns:
            return None
        lower = df[col].fillna('').str.lower()
        cls.cached_col_lower[col] = lower
        return lower

    def _load_data(self):
        """선택된 등급의 Parquet 파일 로드 (년도 + rating set으로 캐시 키)"""
        if (PandasSearchWorker.cached_df is not None and
            PandasSearchWorker.loaded_ratings == self.selected_ratings and
            PandasSearchWorker.loaded_year == self.dataset_year):
            return True

        # rating set 또는 년도가 바뀌면 lowercase 캐시도 무효화
        PandasSearchWorker.cached_df = None
        PandasSearchWorker.cached_col_lower.clear()
        dfs = []

        for rating in self.selected_ratings:
            file_name = f"danbooru_{self.dataset_year}_{rating}.parquet"
            path = os.path.join(self.parquet_dir, file_name)
            
            if os.path.exists(path):
                self.status_update.emit(f"📂 '{rating}' 등급 데이터 로딩 중...")
                try:
                    try:
                        df = pd.read_parquet(path, columns=self.REQUIRED_COLUMNS)
                    except Exception:
                        df = pd.read_parquet(path)
                    dfs.append(df)
                except Exception as e:
                    self.status_update.emit(f"⚠️ 파일 로드 실패 ({rating}): {e}")
            else:
                self.status_update.emit(f"⚠️ 파일 없음: {path}")

        if not dfs:
            self.status_update.emit("❌ 로드된 데이터가 없습니다.")
            return False

        self.status_update.emit(f"📊 {self.dataset_year} 데이터 병합 중...")
        PandasSearchWorker.cached_df = pd.concat(dfs, ignore_index=True)
        PandasSearchWorker.loaded_ratings = self.selected_ratings
        PandasSearchWorker.loaded_year = self.dataset_year
        
        # 문자열 컬럼 결측치 처리
        text_cols = ['copyright', 'character', 'artist', 'general', 'meta'] 
        for col in text_cols:
            if col in PandasSearchWorker.cached_df.columns:
                PandasSearchWorker.cached_df[col] = (
                    PandasSearchWorker.cached_df[col].fillna("")
                )
                
        return True

    def stop(self):
        self.is_running = False