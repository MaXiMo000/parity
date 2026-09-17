import { Bounds, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import { useMemo } from 'react'
import type { Edge as EdgeT, Node as NodeT, VirtualNode as VirtualNodeT } from '../api'
import type { DriftStatus } from '../lib/severity'
import { computeLayout } from './layout'
import { Edge } from './Edge'
import { HubNode } from './HubNode'
import { Node } from './Node'

export function Graph({ nodes, edges, virtualNodes, statuses, onSelect }: {
  nodes: NodeT[]
  edges: EdgeT[]
  virtualNodes: VirtualNodeT[]
  statuses: Record<string, DriftStatus>
  onSelect: (id: string) => void
}) {
  const { nodes: laidOut, virtualNodes: laidOutVirtual } = useMemo(
    () => computeLayout(nodes, edges, virtualNodes), [nodes, edges, virtualNodes],
  )

  return (
    <Canvas camera={{ position: [0, 0, 12], fov: 50 }} dpr={[1, 2]}>
      <color attach="background" args={['#05060B']} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[6, 8, 6]} intensity={1.1} />

      <Bounds key={`${nodes.length}-${edges.length}-${virtualNodes.length}`} fit clip margin={1.5}>
        {edges.map((e) => {
          const a = laidOut.get(e.from_node) ?? laidOutVirtual.get(e.from_node)
          const b = laidOut.get(e.to_node) ?? laidOutVirtual.get(e.to_node)
          if (!a || !b) return null
          return <Edge key={`${e.from_node}-${e.to_node}`} from={[a.x, a.y, a.z]} to={[b.x, b.y, b.z]} />
        })}
        {[...laidOut.values()].map((n) => (
          <Node key={n.id} node={n} status={statuses[n.id] ?? 'unverified_no_schema'} onSelect={onSelect} />
        ))}
        {[...laidOutVirtual.values()].map((n) => (
          <HubNode key={n.id} node={n} />
        ))}
      </Bounds>

      <OrbitControls enableDamping autoRotate={false} makeDefault />

      <EffectComposer>
        <Bloom luminanceThreshold={0.6} luminanceSmoothing={0.3} intensity={0.8} mipmapBlur />
      </EffectComposer>
    </Canvas>
  )
}
