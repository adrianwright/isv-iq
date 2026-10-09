import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { SourceMapEntry } from '../types'
import { BuildingAssessment } from './BuildingAssessment'

const sources: SourceMapEntry[] = [
  {
    source: 'fabric',
    label: 'Fabric IQ',
    status: 'complete',
    queries: ['Account and renewal evidence'],
    summary: 'Structured account evidence retrieved.',
    citations: ['r4'],
    durationMs: 120,
    evidenceCount: 1,
    evidenceNoun: 'sources',
  },
]

describe('BuildingAssessment', () => {
  it('remains visible as a completed six-stage assessment', () => {
    const markup = renderToStaticMarkup(
      <BuildingAssessment sources={sources} draft="" complete />,
    )

    expect(markup).toContain('Assessment completed')
    expect(markup.match(/step-done/g)).toHaveLength(6)
    expect(markup).not.toContain('thinking-dots')
  })
})
