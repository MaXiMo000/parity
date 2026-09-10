import { describe, expect, it } from 'vitest'
import { COLOR, nodeColor } from './severity'

describe('nodeColor', () => {
  it('matched reads the match color', () => {
    expect(nodeColor('matched').color).toBe(COLOR.match)
  })
  it('violated reads the violate color', () => {
    expect(nodeColor('violated').color).toBe(COLOR.violate)
  })
  it('unverified_no_schema reads neutral, dim', () => {
    const c = nodeColor('unverified_no_schema')
    expect(c.color).toBe(COLOR.neutral)
    expect(c.emissiveIntensity).toBeLessThan(0.3)
  })
  it('unverified_no_match reads neutral, dim', () => {
    const c = nodeColor('unverified_no_match')
    expect(c.color).toBe(COLOR.neutral)
    expect(c.emissiveIntensity).toBeLessThan(0.3)
  })
})
