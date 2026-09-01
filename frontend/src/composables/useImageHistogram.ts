/**
 * 이미지 src 를 따라가며 히스토그램을 다시 계산한다.
 *
 * 계산은 브라우저에서 한다 — 프리뷰는 base64, 원본은 file:// 인데 `EditorCanvas` 가
 * 이미 file:// 이미지를 `getImageData` 로 읽고 있어(모자이크 지우개) 캔버스 오염이 없다.
 * 브릿지를 안 거치니 프리뷰가 갱신될 때마다 곧바로 따라간다.
 *
 * 히스토그램 상자와 커브 편집기가 **같은 결과를 나눠 쓴다**. 컴포넌트마다 따로 계산하면
 * 같은 이미지를 두 번 디코드하고, 도착 시점이 어긋나 둘이 다른 그림을 보여줄 수 있다.
 */
import { onBeforeUnmount, shallowRef, ref, watch } from 'vue'
import { computeHistograms, emptyHistograms, sampleSize, type Histograms } from '../utils/histogram'

/** 프리뷰는 짧은 간격으로 연달아 도착한다. 그 사이의 갱신은 합친다. */
const RECOMPUTE_DELAY = 60

export function useImageHistogram(src: () => string, active: () => boolean) {
  // shallowRef — 256칸 배열 넷을 프리뷰마다 깊은 프록시로 감쌀 이유가 없다.
  // 통째로 갈아끼우므로 얕은 반응성이면 파생값이 정확히 따라온다.
  const hists = shallowRef<Histograms>(emptyHistograms())
  const hasData = ref(false)
  const notice = ref('')

  let sampler: HTMLCanvasElement | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  /** 늦게 도착한 옛 이미지가 새 결과를 덮지 않게 하는 세대 번호. */
  let token = 0

  function reset(message: string) {
    hists.value = emptyHistograms()
    hasData.value = false
    notice.value = message
  }

  function recompute() {
    const mine = ++token
    if (!active()) return // 숨어 있는 동안은 계산하지 않는다
    const url = src()
    if (!url) {
      reset('이미지 없음')
      return
    }

    const img = new Image()
    img.onload = () => {
      if (mine !== token) return // 그새 다른 이미지가 왔다
      const { w, h } = sampleSize(img.naturalWidth, img.naturalHeight)
      if (!w || !h) return
      if (!sampler) sampler = document.createElement('canvas')
      sampler.width = w
      sampler.height = h
      const ctx = sampler.getContext('2d', { willReadFrequently: true })
      if (!ctx) return
      // 보간을 켜면 없던 중간값이 생겨 계조 뭉갬이 눈에 안 띄게 뭉개진다.
      ctx.imageSmoothingEnabled = false
      ctx.clearRect(0, 0, w, h)
      ctx.drawImage(img, 0, 0, w, h)
      try {
        const next = computeHistograms(ctx.getImageData(0, 0, w, h).data)
        hists.value = next
        hasData.value = next.count > 0
        notice.value = hasData.value ? '' : '읽을 픽셀 없음'
      } catch {
        // 캔버스가 오염된 경우 — 이 앱에서는 나지 않지만 죽지는 말아야 한다
        reset('픽셀을 읽을 수 없음')
      }
    }
    img.onerror = () => {
      if (mine !== token) return
      reset('이미지를 열 수 없음')
    }
    img.src = url
  }

  function schedule() {
    if (timer) clearTimeout(timer)
    timer = setTimeout(recompute, RECOMPUTE_DELAY)
  }

  watch([src, active], schedule, { immediate: true })

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
    timer = null
    token++ // 진행 중인 로드의 결과를 버린다
  })

  return { hists, hasData, notice }
}
