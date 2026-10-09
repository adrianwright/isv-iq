import type {
  FabricStatus,
  ISVAskRequest,
  ISVAskResult,
  ISVPortfolio,
  ISVStreamEvent,
} from '../types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const FABRIC_STATUS_ENDPOINT = `${API_BASE}/api/fabric/status`
const ISV_ASK_ENDPOINT = `${API_BASE}/api/isv/ask`
const ISV_STREAM_ENDPOINT = `${API_BASE}/api/isv/ask/stream`
const ISV_PORTFOLIO_ENDPOINT = `${API_BASE}/api/isv/portfolio`

export function resolveApiUrl(url: string | undefined | null): string | undefined {
  if (!url) return undefined
  return url.startsWith('/api/') ? `${API_BASE}${url}` : url
}

export class RequestError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'RequestError'
    this.status = status
  }
}

export class StreamError extends Error {
  receivedProgress: boolean

  constructor(message: string, receivedProgress: boolean) {
    super(message)
    this.name = 'StreamError'
    this.receivedProgress = receivedProgress
  }
}

export type StreamFailureDecision = 'validation' | 'terminal-composition' | 'non-streaming-fallback'

export function decideStreamFailure(error: unknown): StreamFailureDecision {
  if (!(error instanceof StreamError)) return 'non-streaming-fallback'
  return error.receivedProgress ? 'terminal-composition' : 'validation'
}

export function authorizationHeaders(accessToken: string | null): Record<string, string> {
  if (accessToken === null) return {}
  if (!accessToken.trim()) throw new Error('Access token is required')
  return { Authorization: ['Bearer', accessToken].join(' ') }
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Keep the status-based fallback for non-JSON responses.
  }
  return `Request failed with ${response.status}`
}

export async function getFabricStatus(): Promise<FabricStatus> {
  const unknown: FabricStatus = { state: 'Unknown', capacityName: '', portalUrl: '' }
  try {
    const response = await fetch(FABRIC_STATUS_ENDPOINT, {
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) return unknown
    return (await response.json()) as FabricStatus
  } catch {
    return unknown
  }
}

export async function getISVPortfolio(accessToken: string | null): Promise<ISVPortfolio> {
  const response = await fetch(ISV_PORTFOLIO_ENDPOINT, {
    headers: {
      Accept: 'application/json',
      ...authorizationHeaders(accessToken),
    },
  })
  if (!response.ok) throw new RequestError(await errorDetail(response), response.status)
  return (await response.json()) as ISVPortfolio
}

export async function askISV(
  question: string,
  accessToken: string | null,
  accountId?: string,
  renewalId?: string,
): Promise<ISVAskResult> {
  const response = await fetch(ISV_ASK_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authorizationHeaders(accessToken),
    },
    body: JSON.stringify(buildISVRequest(question, accountId, renewalId)),
  })
  if (!response.ok) throw new RequestError(await errorDetail(response), response.status)
  return (await response.json()) as ISVAskResult
}

export async function askISVStream(
  question: string,
  onEvent: (event: ISVStreamEvent) => void,
  accessToken: string | null,
  accountId?: string,
  renewalId?: string,
): Promise<void> {
  const response = await fetch(ISV_STREAM_ENDPOINT, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
      ...authorizationHeaders(accessToken),
    },
    body: JSON.stringify(buildISVRequest(question, accountId, renewalId)),
  })
  if (!response.ok) throw new RequestError(await errorDetail(response), response.status)
  if (!response.body) throw new Error(`Stream request failed with ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let receivedProgress = false
  const handleEvent = (event: ISVStreamEvent) => {
    if (event.type === 'error') throw new StreamError(event.data.message, receivedProgress)
    receivedProgress = true
    onEvent(event)
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split(/\r?\n\r?\n/)
    buffer = frames.pop() ?? ''
    for (const frame of frames) emitFrame(frame, handleEvent)
  }
  buffer += decoder.decode()
  if (buffer.trim()) emitFrame(buffer, handleEvent)
}

function buildISVRequest(
  question: string,
  accountId?: string,
  renewalId?: string,
): ISVAskRequest {
  return {
    question,
    ...(accountId ? { accountId } : {}),
    ...(renewalId ? { renewalId } : {}),
  }
}

function emitFrame(frame: string, onEvent: (event: ISVStreamEvent) => void) {
  const lines = frame.split(/\r?\n/)
  let eventType = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return
  onEvent({
    type: eventType,
    data: JSON.parse(dataLines.join('\n')) as unknown,
  } as ISVStreamEvent)
}
