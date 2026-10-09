# Contoso forecast huddle: demo script

Synthetic demo only. Seeded by `agent/provisioning/isv/seed_isv_m365_workiq.py`.

The seeder creates two Work IQ evidence items for ACC-1001 / REN-1001:

1. **Teams conversation** (`[ACC-1001-HUDDLE-THREAD]`): posted to the signed-in user's self-chat, and optionally to a group chat via `--huddle-members`.
2. **Teams meeting** "renewal forecast huddle": created on the signed-in user's calendar with no attendees.

Transcripts only exist after a real meeting runs, so the meeting must be held manually.

## Run the transcribed meeting

1. Open the "renewal forecast huddle" event and join the Teams meeting.
2. Start **Record and transcribe** > **Start transcription** before speaking.
3. Read the lines below (one or more people; one person can read every part).
4. End the meeting. The transcript and recap appear in Teams and become available to Work IQ after a delay.

## Script

- **Jordan Lee:** The three-year proposal is ready to send and all three commitments are complete. Do we keep the full 2.4 million dollars in the forecast?
- **Morgan Patel:** Not yet. Analytics adoption is 53 percent and trending down 14 percent. I can't validate recovery with that trend.
- **Casey Williams:** Two P1 cases are still open and one SLA breach is under monitoring. The recovery package was approved, but the district hasn't confirmed closure.
- **Alex Johnson:** Maya Chen says the new CIO asked for the proposal but hasn't responded on value. I want the forecast held at 2.2 million until we hear back.
- **Jordan Lee:** Agreed. Hold at 2.2 million. I'll own the forecast action, due October 13th. Morgan validates adoption, Alex does the executive review.
- **Riley Nguyen:** Separately, AI Automation is still a credible 450 thousand dollar candidate, pending workshop sponsorship and architecture capacity.

## Re-seeding

```
python agent/provisioning/isv/seed_isv_m365_workiq.py --tenant-id <tenant> --client-id <client>
```

Add `--huddle-members a@contoso.com,b@contoso.com` to also post the thread to a group chat titled "Contoso USD - Renewal forecast huddle". Without the flag nobody else is messaged.

The run is idempotent: the thread is skipped if its tag exists in the target chat, and an existing meeting has its description updated and its Teams meeting re-asserted (the join link may be regenerated).
