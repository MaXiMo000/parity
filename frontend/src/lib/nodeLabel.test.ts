import { describe, expect, it } from 'vitest'
import type { Node } from '../api'
import { nodeLabel } from './nodeLabel'

const restNode: Node = {
  id: '1', kind: 'rest_operation', method: 'GET', path_template: '/pets/{id}',
  operation_id: 'getPet', type_name: null, field_name: null,
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const graphqlNode: Node = {
  id: '2', kind: 'graphql_field', method: null, path_template: null,
  operation_id: null, type_name: 'Query', field_name: 'pet',
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

describe('nodeLabel', () => {
  it('labels a REST node by method and path', () => {
    expect(nodeLabel(restNode)).toEqual({ eyebrow: 'GET · /pets/{id}', title: 'getPet' })
  })

  it('labels a GraphQL node by type and field', () => {
    expect(nodeLabel(graphqlNode)).toEqual({ eyebrow: 'Query field', title: 'pet' })
  })
})
