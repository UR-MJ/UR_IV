/**
 * 브리지 계약 타입 (Vue ↔ PyQt) — App.vue 분할/TypeScript 기반(②).
 *
 * 에디터 전용 타입(빌드는 esbuild가 무시). 액션/이벤트 이름 자동완성 + 페이로드 형태 힌트.
 * `(string & {})` 덕분에 알려진 이름은 자동완성되고, 모르는 문자열도 허용 → 이 파일이
 * 살짝 드리프트해도 에러는 안 남. **이름 정합성의 강제 소스는 tests/test_bridge_contract.py**.
 */

/** Vue가 requestAction()/action()으로 호출하는 백엔드 액션 이름. */
export type ActionName =
  | 'generate' | 'cancel_generation' | 'random_prompt' | 'swap_resolution'
  | 'set_high_res_factor' | 'set_random_resolutions' | 'set_rating_filter' | 'update_prompt_deck'
  | 'set_lora_text' | 'set_lora_stack' | 'set_artist_locked'
  | 'save_settings' | 'save_preset' | 'load_preset' | 'save_preset_by_name'
  | 'load_preset_by_name' | 'delete_preset'
  | 'save_ui_prefs' | 'save_global_weights' | 'save_cond_rules' | 'save_tab_defaults' | 'set_tab_order'
  | 'send_to_i2i' | 'send_to_inpaint' | 'send_to_editor' | 'send_to_compare'
  | 'generate_i2i' | 'generate_inpaint' | 'start_batch' | 'start_upscale' | 'start_xyz_plot'
  | 'run_adetailer_single' | 'run_adetailer_batch' | 'stop_adetailer_batch'
  | 'run_sam3_single' | 'run_sam3_batch' | 'open_ad_files' | 'open_ad_folder'
  | 'open_batch_files' | 'open_upscale_files'
  | 'caption_pick_files' | 'caption_pick_folder' | 'caption_pick_outdir'
  | 'apply_search_result' | 'add_search_to_queue' | 'export_search_results' | 'import_search_results'
  | 'search_events' | 'select_event' | 'event_add_to_queue' | 'event_generate_now'
  | 'export_event_results' | 'import_event_results'
  | 'start_queue' | 'stop_queue' | 'pause_queue' | 'resume_queue' | 'clear_queue'
  | 'remove_queue_items' | 'move_queue_item' | 'update_queue_item' | 'add_image_to_queue'
  | 'editor_open_file' | 'editor_save' | 'editor_save_as' | 'editor_add_yolo_model'
  | 'editor_clear_yolo_models' | 'editor_load_watermark_image'
  | 'open_png_info_file' | 'open_compare_image' | 'pnginfo_send_prompt' | 'pnginfo_generate'
  | 'pull_prompt_from_image' | 'explore_seed' | 'copy_to_clipboard'
  | 'gallery_open_folder' | 'gallery_send_exif_to_t2i' | 'add_favorite' | 'remove_favorite' | 'delete_image'
  | 'toggle_automation' | 'stop_automation' | 'set_automation_settings'
  | 'workflow_profile_list' | 'workflow_profile_save' | 'workflow_profile_load'
  | 'workflow_profile_delete' | 'workflow_profile_rename'
  | 'prompt_order_list' | 'prompt_order_save' | 'prompt_order_reset'
  | 'instant_wildcards_list' | 'instant_wildcards_save' | 'instant_wildcards_delete'
  | 'show_prompt_history' | 'open_lora_manager' | 'show_api_manager' | 'open_url'
  | 'import_anima_from_forge' | 'unload_model_request' | 'show_toast'
  | 'native_tab_switch' | 'vue_tab_switch'
  | 'probe_backend' | 'select_backend' | 'pick_comfy_workflow'
  | (string & {})

/** Python이 vue_bridge에서 emit하고 Vue가 onBackendEvent()로 받는 시그널 이름. */
export type BackendEvent =
  | 'imageGenerated' | 'generationStarted' | 'generationError' | 'generationProgress'
  | 'automationStatus' | 'automationSettingsLoaded'
  | 'searchResultsReady' | 'searchResultLineage' | 'searchStatus' | 'queueUpdated' | 'queueItemAdded' | 'queueCompleted'
  | 'uiPrefsLoaded' | 'condRulesLoaded' | 'loraStackLoaded' | 'loraInserted' | 'globalWeightsLoaded'
  | 'promptOrderLoaded' | 'instantWildcardsList' | 'workflowProfilesList'
  | 'editorImageLoaded' | 'editorWatermarkImageLoaded' | 'editorResult' | 'yoloModelUpdated' | 'i2iImageLoaded' | 'inpaintImageLoaded'
  | 'compareImageLoaded' | 'galleryFolderLoaded' | 'galleryImagesReady' | 'thumbnailReady'
  | 'upscalersReady' | 'ollamaModelsReady' | 'adetailerModelsReady'
  | 'batchFilesSelected' | 'adetailerResult' | 'adetailerProgress' | 'sam3Result' | 'sam3Progress'
  | 'captionFilesSelected' | 'captionProgress' | 'captionDone' | 'captionOutDirSelected'
  | 'eventSearchProgress' | 'eventSearchResults' | 'eventImportResults'
  | 'ollamaResult' | 'genNlResult' | 'vramUpdated' | 'showNotification' | 'tabChanged'
  | 'backendSelectionRequired' | 'backendProbeResult' | 'backendSelected' | 'comfyWorkflowPicked'
  | (string & {})

/** show_toast 페이로드 */
export interface ShowToastPayload { type: 'success' | 'error' | 'info'; msg: string }

/** set_rating_filter 페이로드 — g/s/q/e 중 활성 등급 */
export interface SetRatingFilterPayload { ratings: string[] }

/** set_high_res_factor 페이로드 */
export interface SetHighResPayload { enabled: boolean; factor: number }

/** LoRA 스택 1개 항목 (ui_prefs.loraStack 단일 소스). weight는 set_lora_stack에선 0~3 배율,
 *  loraStack 저장 시엔 정수 퍼센트(weight/100 = 배율). */
export interface LoraEntry {
  name: string
  weight: number
  enabled: boolean
  triggerWords: string[]
}

/** set_lora_stack 페이로드 */
export interface SetLoraStackPayload { entries: LoraEntry[] }

// ── 시작 백엔드 게이트 ──
// 창 위에 뜨는 Vue 오버레이. 예전의 별도 QDialog 를 대체하지만, Vue 가 못 뜨면
// 그릴 방법이 없으므로 QDialog 는 비상 경로로 남아 있다(Python 쪽 폴백).

/** probe_backend 페이로드 — 두 주소를 한 번에 감지 요청 */
export interface ProbeBackendPayload { webuiUrl: string; comfyUrl: string }

/** backendProbeResult 이벤트 — 각 백엔드의 응답 여부 */
export interface BackendProbeResult { webui: 'ok' | 'fail'; comfy: 'ok' | 'fail' }

/** backendSelectionRequired 이벤트 — 게이트를 열 때 쓸 현재 설정값 */
export interface BackendSelectionRequired {
  webuiUrl: string
  comfyUrl: string
  workflowPath: string
}

/** select_backend 페이로드 — url 은 고른 쪽 주소 하나만 보낸다 */
export interface SelectBackendPayload {
  type: 'webui' | 'comfyui'
  url: string
  workflowPath?: string
}

/** backendSelected 이벤트 — 실패해도 게이트는 떠 있어야 하므로 error 를 함께 싣는다 */
export interface BackendSelectedResult { ok: boolean; error?: string }

/** comfyWorkflowPicked 이벤트 — 경로 + analyze_workflow 요약 */
export interface ComfyWorkflowPicked {
  path: string
  info: {
    valid: boolean
    error?: string
    format?: string
    node_count?: number
    ksampler_type?: string
    width?: number
    height?: number
    classification?: string
    is_locked?: boolean
  }
}
