import { describe, expect, it } from 'vitest'
import { COLOR, nodeColor } from './severity'

describe('nodeColor', () => {
  it('matched reads the match color', () => {
    expect(nodeColor('matched').color).toBe(COLOR.match)
  })
  it('violated reads the violate color', () => {
    expect(nodeColor('violated').color).toBe(COLOR.violate)
  })
  it('unverified reads neutral, dim', () => {
    const c = nodeColor('unverified')
    expect(c.color).toBe(COLOR.neutral)
    expect(c.emissiveIntensity).toBeLessThan(0.3)
  })
})
