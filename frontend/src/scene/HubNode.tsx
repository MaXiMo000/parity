import { Text } from '@react-three/drei'
import type { LaidOutVirtualNode } from './layout'

/** A synthetic GraphQL graph landmark (SPEC.md §8.3's "Query and Mutation
 * as roots, fields fanning out to the types they return") -- never a
 * real, sendable API operation, so deliberately not clickable: there is
 * no per-type detail to show (a hub only ever carries a label, never a
 * schema/history/send capability), and no drift status of its own (never
 * --match/--violate, always the neutral palette -- a hub is not itself
 * "verified" or "violated"). A root hub (Query/Mutation) reads as more
 * prominent than a type hub, matching SPEC's own "roots" language: a
 * distinct icosahedron shape and a larger size, vs. a smaller octahedron
 * for an ordinary type hub. */
export function HubNode({ node }: { node: LaidOutVirtualNode }) {
  const isRoot = node.kind === 'graphql_root'

  return (
    <group position={[node.x, node.y, node.z]}>
      <mesh>
        {isRoot ? <icosahedronGeometry args={[0.5, 0]} /> : <octahedronGeometry args={[0.38, 0]} />}
        <meshStandardMaterial
          color="#7C879C"
          emissive="#7C879C"
          emissiveIntensity={isRoot ? 0.25 : 0.12}
          roughness={0.6}
          metalness={0.1}
          wireframe
        />
      </mesh>
      <Text
        position={[0, isRoot ? 0.75 : 0.58, 0]}
        fontSize={isRoot ? 0.24 : 0.18}
        color="#7C879C"
        anchorX="center"
        anchorY="bottom"
      >
        {node.label}
      </Text>
    </group>
  )
}
