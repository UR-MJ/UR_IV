# ui/bridge_editor.py
"""
VueBridge 구조 가이드
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

QWebChannel은 단일 QObject만 등록 가능하므로 VueBridge 클래스는 하나로 유지.
내부 코드는 다음 섹션으로 구분:

== SECTION 1: Signals (Python → Vue) ==
  - imageGenerated, generationStarted, generationError
  - editorImageLoaded, i2iImageLoaded, inpaintImageLoaded
  - widgetValueChanged, widgetPropertyChanged, batchUpdate
  - searchResultsReady, eventSearchResults
  - loraInserted, yoloModelUpdated, compareImageLoaded
  - vramUpdated, ollamaResult, condRulesLoaded
  - queueUpdated, queueItemAdded, queueCompleted
  - showNotification, seedExploreResult, batchFilesSelected

== SECTION 2: Widget Proxy (양방향 동기화) ==
  - onWidgetChanged, getWidgetValue, getAllWidgetValues
  - pushWidgetValue, pushWidgetProperty
  - beginBatchUpdate, endBatchUpdate

== SECTION 3: Generation (이미지 생성) ==
  - send_image, send_start, send_error

== SECTION 4: Editor (이미지 편집) ==
  - editorProcess (19개 연산)

== SECTION 5: Gallery & Favorites ==
  - getGalleryImages, getFavorites
  - getLastGalleryFolder, _save_gallery_folder
  - getImageExif, getPngInfo
  - saveImageExif, renameFile

== SECTION 6: Search & AI ==
  - searchDanbooru, _on_search_results
  - classifyTags, deepCleanPrompt
  - getCharacterInsight, getCharacterTags
  - getTagSuggestions
  - ollamaEnhance, ollamaListModels

== SECTION 7: Tools ==
  - loadImageBase64, getUpscalers
  - getEdgeMap, getYoloModelLabel, refreshYoloModels
  - generateXYZCombinations, processBatchFile
  - getWildcardTree

향후 메서드 추가 시 해당 섹션에 배치할 것.
"""
