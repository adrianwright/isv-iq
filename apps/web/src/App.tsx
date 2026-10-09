import { useEffect, useRef, useState } from 'react'
import {
  askISV,
  askISVStream,
  decideStreamFailure,
  getFabricStatus,
  RequestError,
} from './api/client'
import './App.css'
import { AuthenticationError, useAuthentication } from './authentication'
import { AssessmentFailureCard } from './components/AssessmentFailureCard'
import { BuildingAssessment } from './components/BuildingAssessment'
import { EmptyState } from './components/EmptyState'
import { IQActivityBar } from './components/IQActivityBar'
import { ISVDashboard } from './components/ISVDashboard'
import { QuestionLibrary } from './components/QuestionLibrary'
import { SideNav } from './components/SideNav'
import { TopBar } from './components/TopBar'
import { defaultQuestionExample, type QuestionExample } from './questionLibrary'
import { sourceLabels, sourceOrder, sourceRetrieving } from './sourceMeta'
import type {
  FabricStatus,
  ISVAskResult,
  ISVStreamEvent,
  SourceMapEntry,
  TraceStep,
} from './types'

const SECTION_IDS = ['assessment', 'account', 'specialists', 'evidence', 'workflow', 'sources', 'settings']

function createIdleSourceMap(status: SourceMapEntry['status']): SourceMapEntry[] {
  return sourceOrder.map((source) => ({
    source,
    label: sourceLabels[source],
    status,
    queries: [],
    citations: [],
    retrieving: sourceRetrieving[source],
  }))
}

function App() {
  const { getAccessToken } = useAuthentication()
  const [question, setQuestion] = useState(defaultQuestionExample.prompt)
  const [accountId, setAccountId] = useState(defaultQuestionExample.accountId)
  const [renewalId, setRenewalId] = useState(defaultQuestionExample.renewalId)
  const [result, setResult] = useState<ISVAskResult | null>(null)
  const [sourceMap, setSourceMap] = useState<SourceMapEntry[]>(createIdleSourceMap('idle'))
  const [trace, setTrace] = useState<TraceStep[]>([])
  const [statusMessage, setStatusMessage] = useState(
    'Select or edit a question, then run the customer assessment.',
  )
  const [isLoading, setIsLoading] = useState(false)
  const [darkMode, setDarkMode] = useState(false)
  const [activeSection, setActiveSection] = useState('assessment')
  const [reasoningDraft, setReasoningDraft] = useState('')
  const [fabricStatus, setFabricStatus] = useState<FabricStatus | null>(null)
  const [assessmentFailure, setAssessmentFailure] = useState<string | null>(null)
  const traceTimers = useRef<number[]>([])

  useEffect(() => {
    document.body.classList.toggle('dark', darkMode)
  }, [darkMode])

  useEffect(() => {
    let active = true
    const poll = async () => {
      const status = await getFabricStatus()
      if (active) setFabricStatus(status)
    }
    void poll()
    const interval = window.setInterval(() => void poll(), 30000)
    return () => {
      active = false
      window.clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        if (visible[0]) setActiveSection(visible[0].target.id)
      },
      { rootMargin: '-40% 0px -50% 0px', threshold: [0, 0.25, 0.5] },
    )
    for (const id of SECTION_IDS) {
      const element = document.getElementById(id)
      if (element) observer.observe(element)
    }
    return () => observer.disconnect()
  }, [result])

  function clearTraceTimers() {
    for (const timer of traceTimers.current) window.clearTimeout(timer)
    traceTimers.current = []
  }

  function selectQuestionExample(example: QuestionExample) {
    setQuestion(example.prompt)
    setAccountId(example.accountId)
    setRenewalId(example.renewalId)
  }

  function revealPlanSteps(steps: string[]) {
    clearTraceTimers()
    setTrace([])
    for (const [index, step] of steps.entries()) {
      const timer = window.setTimeout(() => {
        setTrace((current) => [
          ...current,
          {
            step,
            detail: 'Planning source queries and evidence checks.',
            ts: index,
            status: 'in_progress',
          },
        ])
      }, index * 180)
      traceTimers.current.push(timer)
    }
  }

  function handleStreamEvent(event: ISVStreamEvent) {
    switch (event.type) {
      case 'plan':
        setSourceMap(createIdleSourceMap('queued'))
        revealPlanSteps(event.data.steps)
        break
      case 'source_query':
        setSourceMap((current) =>
          current.map((entry) =>
            entry.source === event.data.source
              ? {
                  ...entry,
                  status: 'searching',
                  queries: [event.data.query],
                  retrieving: event.data.retrieving ?? entry.retrieving,
                }
              : entry,
          ),
        )
        break
      case 'source_result':
        setSourceMap((current) =>
          current.map((entry) =>
            entry.source === event.data.source
              ? {
                  ...entry,
                  status: event.data.status,
                  citations: event.data.citations,
                  durationMs: event.data.durationMs,
                  summary: event.data.summary,
                  retrieving: event.data.retrieving ?? entry.retrieving,
                  evidenceCount: event.data.evidenceCount,
                  evidenceNoun: event.data.evidenceNoun,
                }
              : entry,
          ),
        )
        break
      case 'agent_activity':
        if (event.data.phase === 'answer_delta') {
          setReasoningDraft((current) => current + (event.data.text ?? ''))
        }
        break
      case 'final':
        clearTraceTimers()
        setAssessmentFailure(null)
        setResult(event.data.result)
        setSourceMap(event.data.result.sourceMap)
        setTrace(event.data.result.trace)
        setStatusMessage(`${event.data.result.mode === 'mock' ? 'Synthetic' : 'Live'} ISV assessment rendered.`)
        break
      case 'error':
        setStatusMessage(`Stream warning: ${event.data.message}`)
        break
      default:
        break
    }
  }

  async function handleAsk() {
    clearTraceTimers()
    setIsLoading(true)
    setResult(null)
    setSourceMap(createIdleSourceMap('queued'))
    setTrace([])
    setReasoningDraft('')
    setAssessmentFailure(null)
    setStatusMessage('Dispatching the four IQ layers in parallel...')

    let streamReturnedFinal = false
    let streamHadProgress = false
    let accessToken: string | null
    try {
      accessToken = await getAccessToken()
    } catch (error) {
      setSourceMap(createIdleSourceMap('idle'))
      setStatusMessage(
        error instanceof AuthenticationError
          ? error.message
          : 'Microsoft Entra sign-in or token acquisition failed.',
      )
      setIsLoading(false)
      return
    }

    try {
      await askISVStream(
        question,
        (event) => {
          streamHadProgress = true
          if (event.type === 'final') streamReturnedFinal = true
          handleStreamEvent(event)
        },
        accessToken,
        accountId,
        renewalId,
      )
      if (!streamReturnedFinal) throw new Error('Stream closed before final result')
    } catch (streamError) {
      if (streamReturnedFinal) return
      const decision = decideStreamFailure(streamError)
      if (decision === 'validation') {
        setSourceMap(createIdleSourceMap('idle'))
        setStatusMessage(streamError instanceof Error ? streamError.message : 'Invalid request.')
        return
      }
      if (decision === 'terminal-composition') {
        clearTraceTimers()
        const message =
          streamError instanceof Error ? streamError.message : 'The assessment could not be composed.'
        setAssessmentFailure(message)
        setStatusMessage(`Retrieval completed, but composition failed: ${message}`)
        return
      }
      try {
        const fallback = await askISV(question, accessToken, accountId, renewalId)
        setResult(fallback)
        setSourceMap(fallback.sourceMap)
        setTrace(fallback.trace)
        setStatusMessage('Streaming unavailable; rendered the non-streaming assessment.')
      } catch (askError) {
        if (!streamHadProgress) setSourceMap(createIdleSourceMap('idle'))
        const message =
          askError instanceof RequestError
            ? askError.message
            : 'The local ISV API is unavailable. Start it with scripts/dev.ps1.'
        if (streamHadProgress) setAssessmentFailure(message)
        setStatusMessage(message)
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="layout">
      <SideNav
        activeId={activeSection}
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((value) => !value)}
      />
      <div className="main-col">
        <TopBar mode={result?.mode} fabricStatus={fabricStatus} />
        <div className="status-strip">
          <span className={isLoading ? 'loading-dot' : 'ready-dot'} aria-hidden="true" />
          <span>{statusMessage}</span>
        </div>
        <QuestionLibrary
          question={question}
          isLoading={isLoading}
          onQuestionChange={setQuestion}
          onSelectExample={selectQuestionExample}
          onAsk={handleAsk}
        />
        <IQActivityBar entries={sourceMap} />
        {isLoading || result ? (
          <BuildingAssessment
            sources={sourceMap}
            draft={reasoningDraft}
            complete={Boolean(result)}
          />
        ) : null}
        {result ? <ISVDashboard result={result} trace={trace} /> : null}
        {!result && !isLoading && assessmentFailure ? (
          <AssessmentFailureCard message={assessmentFailure} onRetry={() => void handleAsk()} />
        ) : null}
        {!result && !isLoading && !assessmentFailure ? <EmptyState /> : null}
      </div>
    </div>
  )
}

export default App
