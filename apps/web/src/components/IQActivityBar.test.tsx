import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { SourceMapEntry } from '../types'
import { IQActivityBar } from './IQActivityBar'

describe('IQActivityBar citation status', () => {
  it('shows Needs review instead of a citation link when Work IQ has no linkable sources', () => {
    const entry: SourceMapEntry = {
      source: 'work',
      label: 'Work IQ',
      status: 'needs_review',
      queries: ['Find the workflow owner'],
      citations: ['r4'],
      evidenceCount: 0,
      evidenceNoun: 'citations',
      retrieving: 'Open tasks and coordinator ownership',
    }

    const markup = renderToStaticMarkup(<IQActivityBar entries={[entry]} />)

    expect(markup).toContain('Needs review')
    expect(markup).not.toContain('href="#evidence"')
  })

  it('keeps annotation sources accessible while making their review state explicit', () => {
    const entry: SourceMapEntry = {
      source: 'work',
      label: 'Work IQ',
      status: 'needs_review',
      queries: ['Find the workflow owner'],
      citations: ['r4'],
      evidenceCount: 1,
      evidenceNoun: 'sources',
      retrieving: 'Open tasks and coordinator ownership',
    }

    const markup = renderToStaticMarkup(<IQActivityBar entries={[entry]} />)

    expect(markup).toContain('Needs review')
    expect(markup).toContain('Review 1 sources')
    expect(markup).toContain('href="#evidence"')
    expect(markup).toContain('needs-review')
  })
})
