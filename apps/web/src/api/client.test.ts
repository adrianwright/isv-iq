import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  askISV,
  askISVStream,
  authorizationHeaders,
  decideStreamFailure,
  getISVPortfolio,
  RequestError,
  StreamError,
} from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ISV API client', () => {
  it('adds delegated authorization and account context', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ schemaVersion: 'isv.v1' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await askISV('Assess the renewal.', 'delegated-token', 'ACC-1001', 'REN-1001')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/isv/ask')
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect((request.headers as Record<string, string>).Authorization).toMatch(/^Bearer /)
    expect(JSON.parse(String(request.body))).toEqual({
      question: 'Assess the renewal.',
      accountId: 'ACC-1001',
      renewalId: 'REN-1001',
    })
  })

  it('supports explicit anonymous mock requests', () => {
    expect(authorizationHeaders(null)).toEqual({})
    expect(() => authorizationHeaders('  ')).toThrow('Access token is required')
  })

  it('loads the versioned portfolio', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ schemaVersion: 'isv.portfolio.v1', accounts: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    const portfolio = await getISVPortfolio(null)
    expect(portfolio.schemaVersion).toBe('isv.portfolio.v1')
  })

  it('parses final SSE events', async () => {
    const onEvent = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          [
            'event: plan',
            'data: {"steps":["Reviewing renewal"]}',
            '',
            'event: final',
            'data: {"result":{"schemaVersion":"isv.v1"}}',
            '',
          ].join('\n'),
          { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
        ),
      ),
    )

    await askISVStream('Assess renewal.', onEvent, null)

    expect(onEvent).toHaveBeenCalledWith({
      type: 'final',
      data: { result: { schemaVersion: 'isv.v1' } },
    })
  })

  it('does not retry terminal composition failures', () => {
    expect(decideStreamFailure(new StreamError('Composition failed', true))).toBe(
      'terminal-composition',
    )
    expect(decideStreamFailure(new RequestError('Unavailable', 503))).toBe(
      'non-streaming-fallback',
    )
  })
})
