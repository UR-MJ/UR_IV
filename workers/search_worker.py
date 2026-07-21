# workers/search_worker.py
import os
import re
import threading
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

class PandasSearchWorker(QThread):
    """Pandas를 이용한 검색 워커"""
    results_ready = pyqtSignal(list, int)
    status_update = pyqtSignal(str)

    # 클래스 전역 캐시(cached_df/cached_col_lower) 보호 — 이전 워커가 1초 내 종료되지
    # 않아 새 워커와 겹칠 때, 서로 다른 연도/등급 로드가 캐시를 동시 변이해 인덱스 불일치
    # 마스크/오데이터/RAM 중복이 나던 경합 방지. run() 전체를 직렬화한다(검색은 사실상
    # 사용자 직렬이라 동시성 손실 무해).
    _run_lock = threading.RLock()

    # 검색에 필요한 컬럼만 로드 (메모리 절약)
    # image_width/height 추가 — 자동(PARQUET) 해상도 + Search 결과 해상도 표기용.
    # 파일별 스키마와 교집합만 읽고, 없는 컬럼은 로드 후 기본값으로 보충한다.
    # 'rating'을 반드시 포함 — 빠지면 2026_06처럼 모든 컬럼이 존재하는 슬림
    # 데이터셋에서 columns= subset이 성공하면서 rating을 안 실어 RATING이 '?'가 됨.
    # 세대별 meta/metadata 차이는 _load_data에서 정규화한다.
    REQUIRED_COLUMNS = ['rating', 'copyright', 'character', 'artist', 'general', 'meta',
                        'image_width', 'image_height']

    cached_df = None
    cached_col_lower = {}  # {col_name: lowercase Series} — rating/year 변경 시 무효화
    loaded_ratings = set()
    loaded_year = ''       # 현재 캐시에 로드된 년도 ('2025' | '2026' | '')

    # 사용 가능한 데이터셋 — dataset_year가 파일 prefix가 됨:
    #   '2025'    → danbooru_2025_{rating}.parquet
    #   '2026'    → danbooru_2026_{rating}.parquet      (기존 풀 데이터)
    #   '2026_06' → danbooru_2026_06_{rating}.parquet   (슬림: rating/해상도/태그/score)
    AVAILABLE_YEARS = ('2026_06', '2026', '2025')
    DEFAULT_YEAR = '2026_06'

    # 결과로 내보내는 컬럼 — bridge의 dict 재구성(_pick/_dim)이 읽는 키만.
    # to_dict 전에 이 컬럼만 남겨 안 쓰는 컬럼(meta, 전체컬럼 폴백분)의 복제를 제거.
    OUTPUT_COLUMNS = ['rating', 'copyright', 'character', 'artist', 'general',
                      'image_width', 'image_height',
                      'tag_string_copyright', 'tag_string_character',
                      'tag_string_artist', 'tag_string_general']

    def __init__(self, parquet_dir, selected_ratings, queries, exclude_queries=None,
                 combine_mode: str = 'and', dataset_year: str = None,
                 result_cap: int = None):
        """
        :param queries: { col: 'pattern' } 포함 검색 — 필드 간 결합은 combine_mode로 제어
        :param exclude_queries: { col: 'pattern' } 제외 검색 — 모드와 무관하게
            언제나 AND-NOT (제외는 "이건 절대 안 됨"의 의미라 OR 모드여도 항상 제외 적용)
        :param combine_mode: 'and' (교집합) | 'or' (합집합) — 필드 간 결합 방식
        :param dataset_year: '2026' (기본) | '2025' — 데이터셋 년도 선택
            2026은 2025를 포함하는 확장판이므로 둘을 동시 선택할 필요 없음
        :param result_cap: 결과 행 수 상한 (무작위 샘플, 무편향). None = 무제한.
            워커 단계에서 자르면 '전체 결과 list[dict] 물질화'가 사라져 피크 RAM이 준다.
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
        self.result_cap = int(result_cap) if result_cap else None
        self.is_running = True

    def run(self):
        """검색 실행 — 클래스 락으로 직렬화(공유 캐시 경합 방지). 대체된 워커는
        락을 기다리는 동안에도 is_running=False면 즉시 빠져나간다."""
        try:
            if not self.is_running:   # 이미 대체됨 — 락 잡기 전 빠른 탈출
                return
            with PandasSearchWorker._run_lock:
                self._run_locked()
        except Exception as e:
            self.status_update.emit(f"❌ 오류 발생: {str(e)}")
            self.results_ready.emit([], 0)

    def _run_locked(self):
        try:
            if not self._load_data():
                return
            if not self.is_running:   # 새 검색으로 대체됨 — stale 결과 emit 금지
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
                    if not self.is_running:
                        return
                    cm = self._parse_condition(df, col, search_text)
                    n_match = int(cm.sum())
                    print(f"[Search] OR  | {col:>10s} '{search_text[:60]}...' → {n_match:,} matches{_wc_note(n_match)}")
                    total_mask |= cm
            else:
                # AND: True에서 시작해 &= 누적
                total_mask = pd.Series(True, index=df.index)
                for col, search_text in non_empty_fields:
                    if not self.is_running:
                        return
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
                if not self.is_running:
                    return
                exclude_mask = self._parse_condition(df, col, search_text)
                n_excl = int(exclude_mask.sum())
                print(f"[Search] EXC | {col:>10s} '{search_text[:60]}...' → {n_excl:,} excluded")
                total_mask &= ~exclude_mask

            # 결과 필터링
            filtered_df = df[total_mask]
            total_count = len(filtered_df)
            print(f"[Search] === DONE === final mask: {int(total_mask.sum()):,} → {total_count:,} rows")

            # cap을 여기(워커)에서 적용 — 전체 결과의 dict 물질화 자체를 회피.
            # sample()은 무작위라 기존 '셔플 후 슬라이스'와 동등(무편향).
            if self.result_cap and total_count > self.result_cap:
                print(f"[Search] capping {total_count:,} → {self.result_cap:,} (워커 단계, RAM 절약)")
                filtered_df = filtered_df.sample(n=self.result_cap)

            # 출력 컬럼만 — 검색용으로만 쓰는 meta/전체컬럼 폴백분 복제 제거
            out_cols = [c for c in self.OUTPUT_COLUMNS if c in filtered_df.columns]
            if out_cols:
                filtered_df = filtered_df[out_cols]

            final_df = filtered_df.fillna("")
            results = final_df.to_dict('records')

            if not self.is_running:   # emit 직전 최종 체크
                return
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
            if not self.is_running:   # 새 검색으로 대체됨 — 비싼 parquet 로드 중단
                return False
            # dataset_year가 그대로 prefix — '2026_06'이면 danbooru_2026_06_{rating}.parquet
            file_name = f"danbooru_{self.dataset_year}_{rating}.parquet"
            path = os.path.join(self.parquet_dir, file_name)

            if os.path.exists(path):
                self.status_update.emit(f"📂 '{rating}' 등급 데이터 로딩 중...")
                try:
                    # 데이터셋 세대별로 meta/metadata 및 해상도 컬럼 유무가 다르다.
                    # columns= 호출 실패를 전체 컬럼 로드로 처리하면 0.4~0.8GB 파일에서
                    # score/fav_count 등 불필요한 컬럼까지 읽게 되므로 스키마 교집합만 로드한다.
                    import pyarrow.parquet as pq
                    schema_names = set(pq.ParquetFile(path).schema.names)
                    columns = [c for c in self.REQUIRED_COLUMNS if c in schema_names]
                    if 'meta' not in schema_names and 'metadata' in schema_names:
                        columns.append('metadata')
                    df = pd.read_parquet(path, columns=columns)
                    if 'metadata' in df.columns and 'meta' not in df.columns:
                        df.rename(columns={'metadata': 'meta'}, inplace=True)
                    for col in self.REQUIRED_COLUMNS:
                        if col not in df.columns:
                            df[col] = None if col in ('image_width', 'image_height') else ''
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
