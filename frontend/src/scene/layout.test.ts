import { describe, expect, it } from 'vitest'
import { computeLayout } from './layout'
import type { Edge, Node, VirtualNode } from '../api'

const node = (id: string): Node => ({
  id, kind: 'rest_operation', method: 'GET', path_template: '/x',
  operation_id: id, type_name: null, field_name: null,
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
})

describe('computeLayout', () => {
  it('returns every input node with real finite coordinates', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges: Edge[] = [{ from_node: 'a', to_node: 'b' }]
    const { nodes: laidOut } = computeLayout(nodes, edges)
    expect([...laidOut.keys()].sort()).toEqual(['a', 'b', 'c'])
    for (const n of laidOut.values()) {
      expect(Number.isFinite(n.x)).toBe(true)
      expect(Number.isFinite(n.y)).toBe(true)
      expect(Number.isFinite(n.z)).toBe(true)
    }
  })

  it('places virtual (hub) nodes in the same simulation and keeps them out of the real-node map', () => {
    const nodes = [node('pet')]
    const virtualNodes: VirtualNode[] = [{ id: 'root:Query', label: 'Query', kind: 'graphql_root' }]
    const edges: Edge[] = [{ from_node: 'root:Query', to_node: 'pet' }]
    const { nodes: laidOut, virtualNodes: laidOutVirtual } = computeLayout(nodes, edges, virtualNodes)

    expect([...laidOut.keys()]).toEqual(['pet'])
    expect([...laidOutVirtual.keys()]).toEqual(['root:Query'])
    const hub = laidOutVirtual.get('root:Query')!
    expect(Number.isFinite(hub.x)).toBe(true)
    expect(Number.isFinite(hub.y)).toBe(true)
    expect(Number.isFinite(hub.z)).toBe(true)
  })

  it('defaults to no virtual nodes when none are passed (REST workspaces)', () => {
    const { virtualNodes } = computeLayout([node('a')], [])
    expect(virtualNodes.size).toBe(0)
  })
})
