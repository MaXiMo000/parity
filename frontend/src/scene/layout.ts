// @ts-expect-error — d3-force-3d ships no published types.
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceX, forceY, forceZ } from 'd3-force-3d'
import type { Edge, Node } from '../api'
import type { DriftStatus } from '../lib/severity'

export interface LaidOutNode extends Node {
  x: number
  y: number
  z: number
  status: DriftStatus
}

const SETTLE_TICKS = 300

export function computeLayout(
  nodes: Node[],
  edges: Edge[],
  statuses: Record<string, DriftStatus>,
): Map<string, LaidOutNode> {
  const simNodes = nodes.map((n) => ({ ...n }))
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
  for (const n of simNodes as (Node & { x: number; y: number; z: number })[]) {
    out.set(n.id, { ...n, x: n.x, y: n.y, z: n.z, status: statuses[n.id] ?? 'unverified' })
  }
  return out
}
