import { describe, expect, it } from 'vitest'
import { BASE_RADIUS, MAX_RADIUS, nodeRadius } from './nodeSize'

describe('nodeRadius', () => {
  it('never-called nodes render at the original fixed radius (no regression)', () => {
    expect(nodeRadius(0)).toBe(BASE_RADIUS)
  })

  it('grows monotonically with call count', () => {
    expect(nodeRadius(1)).toBeGreaterThan(nodeRadius(0))
    expect(nodeRadius(10)).toBeGreaterThan(nodeRadius(1))
    expect(nodeRadius(1000)).toBeGreaterThan(nodeRadius(10))
  })

  it('is capped so one hot node cannot dwarf the graph', () => {
    expect(nodeRadius(1_000_000)).toBe(MAX_RADIUS)
  })
})
