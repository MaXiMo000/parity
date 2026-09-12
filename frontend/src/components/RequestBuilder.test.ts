import { describe, expect, it } from 'vitest'
import type { Node, Workspace } from '../api'
import { guessBody, guessUrl } from './RequestBuilder'

const baseWorkspace: Workspace = {
  id: 'w1', name: 'Test', schema_kind: 'openapi', base_path: '/api/v3',
  schema_source: 'https://petstore3.swagger.io/api/v3/openapi.json',
  has_credential: false, credential_header_name: null,
  nodes: [], edges: [],
}

const restNode: Node = {
  id: 'n1', kind: 'rest_operation', method: 'GET', path_template: '/pet/{petId}',
  operation_id: 'getPetById', type_name: null, field_name: null,
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const graphqlNode: Node = {
  id: 'n2', kind: 'graphql_field', method: null, path_template: null,
  operation_id: null, type_name: 'Query', field_name: 'pet',
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const mutationNode: Node = { ...graphqlNode, id: 'n3', type_name: 'Mutation', field_name: 'addPet' }

describe('guessUrl', () => {
  it('builds a real REST URL from origin + base_path + path_template', () => {
    expect(guessUrl(baseWorkspace, restNode)).toBe('https://petstore3.swagger.io/api/v3/pet/{petId}')
  })

  it('uses schema_source directly for a GraphQL node', () => {
    const ws: Workspace = { ...baseWorkspace, schema_kind: 'graphql', schema_source: 'https://countries.trevorblades.com/graphql' }
    expect(guessUrl(ws, graphqlNode)).toBe('https://countries.trevorblades.com/graphql')
  })

  it('returns empty string for a pasted schema (no real URL to guess from)', () => {
    const ws: Workspace = { ...baseWorkspace, schema_source: 'pasted' }
    expect(guessUrl(ws, restNode)).toBe('')
  })

  it('returns empty string for a REST node with no path_template', () => {
    const nodeWithNoPath: Node = { ...restNode, path_template: null }
    expect(guessUrl(baseWorkspace, nodeWithNoPath)).toBe('')
  })

  it('returns empty string for a malformed http-prefixed schema_source', () => {
    const ws: Workspace = { ...baseWorkspace, schema_source: 'http://' }
    expect(guessUrl(ws, restNode)).toBe('')
  })
})

describe('guessBody', () => {
  it('returns empty string for a REST node', () => {
    expect(guessBody(restNode)).toBe('')
  })

  it('builds a shorthand query skeleton for a Query field', () => {
    expect(guessBody(graphqlNode)).toBe(JSON.stringify({ query: '{ pet }' }, null, 2))
  })

  it('builds an explicit mutation skeleton for a Mutation field', () => {
    expect(guessBody(mutationNode)).toBe(JSON.stringify({ query: 'mutation { addPet }' }, null, 2))
  })
})
