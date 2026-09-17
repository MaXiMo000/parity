// @ts-expect-error — d3-force-3d ships no published types.
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceX, forceY, forceZ } from 'd3-force-3d'
import type { Edge, Node, VirtualNode } from '../api'

export interface LaidOutNode extends Node {
  x: number
  y: number
  z: number
}

export interface LaidOutVirtualNode extends VirtualNode {
  x: number
  y: number
  z: number
}

export interface LayoutResult {
  nodes: Map<string, LaidOutNode>
  virtualNodes: Map<string, LaidOutVirtualNode>
}

const SETTLE_TICKS = 300

// GraphQL's synthetic root/type hubs (SPEC.md §8.3) join the same force
// simulation as real nodes -- their edges (e.g. "root:Query" -> a real
// field id) need a real position on both ends to draw a line between, and
// letting one simulation place everything keeps hubs sitting naturally at
// the center of the fields that actually point to them, rather than a
// second, independently-tuned layout pass fighting the first.
export function computeLayout(nodes: Node[], edges: Edge[], virtualNodes: VirtualNode[] = []): LayoutResult {
  const realIds = new Set(nodes.map((n) => n.id))
  const simNodes = [...nodes, ...virtualNodes].map((n) => ({ ...n }))
  const simLinks = edges.map((e) => ({ source: e.from_node, target: e.to_node }))

  const sim = forceSimulation(simNodes, 3)
    .force('link', forceLink(simLinks).id((d: { id: string }) => d.id).distance(2.2))
    .force('charge', forceManyBody().strength(-6))
    .force('center', forceCenter())
    .force('x', forceX(0).strength(0.05))
    .force('y', forceY(0).strength(0.05))
    .force('z', forceZ(0).strength(0.05))
    .stop()

  for (let i = 0; i < SETTLE_TICKS; i++) sim.tick()

  const out = new Map<string, LaidOutNode>()
  const virtualOut = new Map<string, LaidOutVirtualNode>()
  for (const n of simNodes as ((Node | VirtualNode) & { x: number; y: number; z: number })[]) {
    if (realIds.has(n.id)) out.set(n.id, { ...n, x: n.x, y: n.y, z: n.z } as LaidOutNode)
    else virtualOut.set(n.id, { ...n, x: n.x, y: n.y, z: n.z } as LaidOutVirtualNode)
  }
  return { nodes: out, virtualNodes: virtualOut }
}
