import type { Node } from '../api'

/** DetailPanel's "what is this node" header line, factored out so it's
 * testable without a DOM. node.kind decides which side of the REST/GraphQL
 * fields is the real one -- the other side is always null (SPEC.md §7.5). */
export function nodeLabel(node: Node): { eyebrow: string; title: string } {
  if (node.kind === 'graphql_field') {
    return { eyebrow: `${node.type_name} field`, title: node.field_name ?? '' }
  }
  return { eyebrow: `${node.method} · ${node.path_template}`, title: node.operation_id ?? '' }
}
