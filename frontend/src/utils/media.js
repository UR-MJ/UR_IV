/**
 * 이미지/미디어 URL 헬퍼 — 실행 모드에 맞는 src 생성.
 *
 *  - Qt 임베드 모드(run_gui.bat): QWebEngineView 는 로컬 file:/// 를 직접 로드.
 *    → 기존과 100% 동일하게 `file:///<path>` 반환 (동작 보존).
 *  - 웹 모드(run_WEB_gui.bat): 원격 브라우저는 file:/// 를 못 읽으므로
 *    Python 정적 서버의 `/file?path=` 엔드포인트로 HTTP 서빙.
 *
 * 즉 컴포넌트는 경로(raw path)만 다루고, 화면 표시용 src 는 항상 이 헬퍼를 거친다.
 */

// 웹 모드 감지 — Python 정적 서버가 index.html 에 주입한 전역으로 판별.
// 호출 시점마다 window 를 확인한다(모듈 로드 시점 1회 캡처는 주입 타이밍에 취약).
function _detectWeb() {
  return typeof window !== 'undefined' &&
    !!(window.__AISTUDIO_WS_PORT__ || window.__AISTUDIO_WS_URL__)
}

/**
 * 로컬 파일 경로 → 화면 표시용 src.
 * @param {string} [path]  로컬 파일 경로(또는 이미 file:/// 가 붙은 경로)
 * @param {boolean} [bust]  true 면 캐시 무력화용 타임스탬프 쿼리 추가
 * @returns {string}
 */
export function mediaUrl(path, bust = false) {
  if (!path) return ''
  const s = String(path)
  // 이미 완성된 URL(생성결과 미리보기, data/blob 등)이면 그대로 둔다
  if (/^(https?:|data:|blob:)/i.test(s)) return s
  // file:/// 접두사 제거 → 순수 경로
  const clean = s.replace(/^file:\/\/\//, '').replace(/^file:\/\//, '')
  let url
  if (_detectWeb()) {
    url = '/file?path=' + encodeURIComponent(clean)
  } else {
    url = 'file:///' + clean
  }
  if (bust) url += (url.includes('?') ? '&' : '?') + 't=' + Date.now()
  return url
}

/** 웹 갤러리 카드용 축소 URL. Qt 임베드 모드는 원본 file URL을 그대로 사용한다. */
export function thumbnailUrl(path, width = 384) {
  if (!path) return ''
  if (!_detectWeb()) return mediaUrl(path)
  const s = String(path)
  if (/^(data:|blob:)/i.test(s)) return s
  if (/^https?:/i.test(s)) return s
  const clean = s.replace(/^file:\/\/\//, '').replace(/^file:\/\//, '')
  const safeWidth = Math.max(64, Math.min(1024, Math.round(Number(width) || 384)))
  return '/thumbnail?path=' + encodeURIComponent(clean) + '&width=' + safeWidth
}

/** 웹 모드 여부 (컴포넌트에서 분기 필요 시) */
export function isWebMode() { return _detectWeb() }
