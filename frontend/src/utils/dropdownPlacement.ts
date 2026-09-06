/** Keep a teleported menu within the viewport without moving its trigger. */
export function dropdownPlacement(
  rect: { left: number; top: number; bottom: number; width: number },
  viewport: { width: number; height: number },
  preferredHeight = 240,
) {
  const margin = 8, gap = 4
  const below = Math.max(0, viewport.height - rect.bottom - margin - gap)
  const aboveSpace = Math.max(0, rect.top - margin - gap)
  const above = below < preferredHeight && aboveSpace > below
  const width = Math.min(rect.width, Math.max(0, viewport.width - margin * 2))
  return {
    above,
    left: Math.max(margin, Math.min(rect.left, viewport.width - width - margin)),
    width,
    maxHeight: Math.min(preferredHeight, above ? aboveSpace : below),
    ...(above
      ? { bottom: Math.max(margin, viewport.height - rect.top + gap) }
      : { top: Math.max(margin, rect.bottom + gap) }),
  }
}
