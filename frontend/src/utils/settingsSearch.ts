export interface SettingSearchEntry { id: string; tab: string; title: string; keywords?: string }

export function normalizeSettingSearch(value: string): string {
  return value.normalize('NFKC').toLocaleLowerCase().replace(/[\s·_./-]+/g, '')
}

export function searchSettings(entries: SettingSearchEntry[], query: string): SettingSearchEntry[] {
  const key = normalizeSettingSearch(query)
  if (!key) return []
  return entries.filter(entry => normalizeSettingSearch(`${entry.title} ${entry.keywords || ''}`).includes(key))
    .sort((a, b) => Number(normalizeSettingSearch(b.title) === key) - Number(normalizeSettingSearch(a.title) === key))
}
