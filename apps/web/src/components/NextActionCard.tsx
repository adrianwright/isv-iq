import { CalendarClock, CheckSquare, Hash, User } from 'lucide-react'
import type { NextAction } from '../types'

interface NextActionCardProps {
  action: NextAction
}

/** Renders the drafted next action as a checklist of structured steps (never split from prose) plus
 * owner and task metadata. */
export function NextActionCard({ action }: NextActionCardProps) {
  const steps = action.steps && action.steps.length ? action.steps : [action.text]
  return (
    <section className="rail-card">
      <div className="rail-card-head">
        <CheckSquare size={14} strokeWidth={2.4} aria-hidden="true" />
        Next action
      </div>
      <ul className="rail-steps">
        {steps.map((step, index) => (
          <li key={index}>
            <CheckSquare size={15} strokeWidth={2} aria-hidden="true" />
            <span>{step}</span>
          </li>
        ))}
      </ul>
      <dl className="rail-meta">
        <div>
          <dt>
            <User size={13} strokeWidth={2.2} aria-hidden="true" /> Owner
          </dt>
          <dd>{action.owner.display}</dd>
        </div>
        <div>
          <dt>
            <CalendarClock size={13} strokeWidth={2.2} aria-hidden="true" /> Due
          </dt>
          <dd>{action.due}</dd>
        </div>
        {action.taskId ? (
          <div>
            <dt>
              <Hash size={13} strokeWidth={2.2} aria-hidden="true" /> Task
            </dt>
            <dd>{action.taskId}</dd>
          </div>
        ) : null}
      </dl>
      <span className="task-status">{action.taskStatus || 'Drafted (not submitted)'}</span>
    </section>
  )
}
