interface EmptyStateProps {
  isLoading?: boolean
}

export function EmptyState({ isLoading = false }: EmptyStateProps) {
  return (
    <section className="empty-state card" id="assessment">
      <div className="empty-mark" aria-hidden="true">
        {isLoading ? '...' : 'IQ'}
      </div>
      <h2>{isLoading ? 'Running assessment' : 'Ready to assess customer renewal readiness'}</h2>
      <p>
        {isLoading
          ? 'The four IQ layers are retrieving business knowledge, operational data, workplace context, and external evidence in parallel.'
          : 'Select or edit a question above. The four IQ layers will prepare a cited renewal and expansion assessment for human review.'}
      </p>
    </section>
  )
}
