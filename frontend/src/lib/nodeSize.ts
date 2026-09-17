// SPEC.md §8.3: "Size = real call frequency (node.call_count) -- a node
// that's actually been exercised a lot is visibly more load-bearing than
// one nobody's ever called, a real signal, not decoration." Log-scaled
// so a handful of early calls is already visible (linear scaling would
// make the difference between 0 and 1 calls imperceptible) and capped so
// one hot node never dwarfs the rest of the graph or clips through
// neighbors the force layout placed close by.
export const BASE_RADIUS = 0.55
export const MAX_RADIUS = 1.1
const GROWTH = 0.12

export function nodeRadius(callCount: number): number {
  if (callCount <= 0) return BASE_RADIUS
  return Math.min(BASE_RADIUS + GROWTH * Math.log2(1 + callCount), MAX_RADIUS)
}
