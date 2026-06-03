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
    loaded_ratings = set()

    def __init__(self, parquet_dir, selected_ratings, queries, exclude_queries=None,
                 combine_mode: str = 'and'):
        """
        :param queries: { col: 'pattern' } 포함 검색 — 필드 간 결합은 combine_mode로 제어
        :param exclude_queries: { col: 'pattern' } 제외 검색 — 모드와 무관하게
            언제나 AND-NOT (제외는 "이건 절대 안 됨"의 의미라 OR 모드여도 항상 제외 적용)
        :param combine_mode: 'and' (교집합) | 'or' (합집합) — 필드 간 결합 방식
        """
        super().__init__()
        self.parquet_dir = parquet_dir
        self.selected_ratings = set(selected_ratings)
        self.queries = queries
        self.exclude_queries = exclude_queries or {}
        self.combine_mode = (combine_mode or 'and').lower()
        if self.combine_mode not in ('and', 'or'):
            self.combine_mode = 'and'
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

            df = self.cached_df

            # ── 포함 검색 — 필드 간 결합은 combine_mode에 따라 ──
            # AND: 모든 필드 조건을 만족해야 함 (교집합)
            # OR : 하나라도 만족하면 됨 (합집합) — 단, 비어있는 필드는 제외
            non_empty_fields = [
                (col, txt) for col, txt in self.queries.items()
                if txt and col in df.columns
            ]

            if not non_empty_fields:
                # 검색어 자체가 없으면 모든 행 매칭
                total_mask = pd.Series(True, index=df.index)
            elif self.combine_mode == 'or':
                # OR: 빈 마스크에서 시작해 |= 누적
                total_mask = pd.Series(False, index=df.index)
                for col, search_text in non_empty_fields:
                    total_mask |= self._parse_condition(df, col, search_text)
            else:
                # AND: True에서 시작해 &= 누적 (기존 동작)
                total_mask = pd.Series(True, index=df.index)
                for col, search_text in non_empty_fields:
                    total_mask &= self._parse_condition(df, col, search_text)

            # ── 제외 검색 — 모드와 무관하게 항상 AND-NOT ──
            # 제외 조건은 "이건 절대 안 됨"의 의미라, OR 모드에서도 모두 적용해 빼야 함.
            for col, search_text in self.exclude_queries.items():
                if not search_text:
                    continue
                if col not in df.columns:
                    continue
                exclude_mask = self._parse_condition(df, col, search_text)
                total_mask &= ~exclude_mask

            # 결과 필터링
            filtered_df = df[total_mask]
            total_count = len(filtered_df)

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
        """
        from core.tag_matcher import filter_dataframe
        return filter_dataframe(df, col, query_text, default_combine=self.combine_mode)

    def _load_data(self):
        """선택된 등급의 Parquet 파일 로드"""
        if (PandasSearchWorker.cached_df is not None and 
            PandasSearchWorker.loaded_ratings == self.selected_ratings):
            return True

        PandasSearchWorker.cached_df = None 
        dfs = []
        
        for rating in self.selected_ratings:
            file_name = f"danbooru_2026_{rating}.parquet"
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

        self.status_update.emit("📊 데이터 병합 중...")
        PandasSearchWorker.cached_df = pd.concat(dfs, ignore_index=True)
        PandasSearchWorker.loaded_ratings = self.selected_ratings
        
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