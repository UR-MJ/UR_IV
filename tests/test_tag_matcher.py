"""tag_matcher 매칭 — 제외 리스트 OR 결합 + 공백/언더스코어 양쪽 매칭 회귀.

심층 검색 제외 버그: 제외 리스트가 검색 모드(AND)로 결합돼 '나열한 걸 모두 동시에 가진 행'만
제외 → 거의 안 빠졌음. 제외는 항상 OR 결합이어야 함. 또 입력은 공백(monkey d. luffy)인데
데이터는 언더스코어(monkey_d._luffy)여도 매칭돼야 함.
"""
import unittest

try:
    import pandas as pd
    from core.tag_matcher import filter_dataframe
    _HAS_PANDAS = True
except Exception:
    _HAS_PANDAS = False


@unittest.skipUnless(_HAS_PANDAS, "pandas/tag_matcher 미설치")
class TestTagMatcherExclude(unittest.TestCase):
    def _df(self):
        return pd.DataFrame({'character': [
            'monkey_d._luffy, sanji_(one_piece)',   # luffy 포함
            'kaeya_(genshin_impact)',                # kaeya 포함
            'random_char, other_tag',                # 둘 다 없음
        ]})

    def test_space_input_matches_underscore_data(self):
        # 공백 입력이 언더스코어 데이터와 매칭 (단일 태그)
        mask = filter_dataframe(self._df(), 'character', 'monkey d. luffy', default_combine='and')
        self.assertEqual(list(mask), [True, False, False])

    def test_exclude_list_or_combines(self):
        # 제외 리스트는 OR — 어느 하나라도 매칭하면 True (이게 제외 대상)
        q = 'monkey d. luffy, kaeya (genshin impact)'
        mask_or = filter_dataframe(self._df(), 'character', q, default_combine='or')
        self.assertEqual(list(mask_or), [True, True, False])

    def test_and_combine_was_the_bug(self):
        # AND로 결합하면(기존 버그) 둘을 동시에 가진 행이 없어 전부 False → 아무것도 제외 안 됨
        q = 'monkey d. luffy, kaeya (genshin impact)'
        mask_and = filter_dataframe(self._df(), 'character', q, default_combine='and')
        self.assertEqual(list(mask_and), [False, False, False])


if __name__ == "__main__":
    unittest.main()
