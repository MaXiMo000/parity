import { describe, expect, it } from 'vitest'
import { computeLayout } from './layout'
import type { Edge, Node } from '../api'

const node = (id: string): Node => ({
  id, kind: 'rest_operation', method: 'GET', path_template: '/x',
  operation_id: id, declared_request_schema: null, declared_response_schema: null, call_count: 0,
})

describe('computeLayout', () => {
  it('returns every input node with real finite coordinates', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges: Edge[] = [{ from_node: 'a', to_node: 'b' }]
    const laidOut = computeLayout(nodes, edges)
    expect([...laidOut.keys()].sort()).toEqual(['a', 'b', 'c'])
    for (const n of laidOut.values()) {
      expect(Number.isFinite(n.x)).toBe(true)
      expect(Number.isFinite(n.y)).toBe(true)
      expect(Number.isFinite(n.z)).toBe(true)
    }
  })
})
