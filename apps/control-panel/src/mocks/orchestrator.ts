import type { EventEnvelope, RunResponse } from '../generated/contracts';
export const mockRun: RunResponse = { run_id: 'run-demo-7f3a', state: 'PO_RUNNING', current_stage: 'PO · analisando briefing', created_at: '2026-08-22T16:00:00.000Z', duration_ms: 128000, active_container: 'po-worker-7f3a' };
export const mockEvents: EventEnvelope[] = [
  { event_id: 'evt-1', sequence: 1, run_id: mockRun.run_id, actor: 'system', type: 'BRIEFING_RECEIVED', correlation_id: 'NC-003', causation_id: null, ts: '2026-08-22T16:00:00.000Z', payload: { summary: 'Briefing recebido e execução criada' } },
  { event_id: 'evt-2', sequence: 2, run_id: mockRun.run_id, actor: 'po', type: 'PO_STARTED', correlation_id: 'NC-003', causation_id: 'evt-1', ts: '2026-08-22T16:00:04.000Z', payload: { container: 'po-worker-7f3a', stage: 'PO' } },
  { event_id: 'evt-3', sequence: 3, run_id: mockRun.run_id, actor: 'system', type: 'CONTEXT_AUTHORIZED', correlation_id: 'NC-003', causation_id: 'evt-2', ts: '2026-08-22T16:00:06.000Z', payload: { manifest_hash: 'sha256:demo' } }
];
