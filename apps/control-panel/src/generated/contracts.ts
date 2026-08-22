/** Adapter for packages/contracts. Replace with the generated package when I1-001 is merged. */
export type RunState = 'RECEIVED' | 'PO_QUEUED' | 'PO_RUNNING' | 'BACKLOG_FROZEN' | 'DEV_RUNNING' | 'QA_RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELED' | 'NEEDS_HUMAN';
export type EventActor = 'system' | 'po' | 'dev' | 'qa' | 'runner';
export interface CreateRunRequest { briefing: string; idempotency_key?: string }
export interface RunResponse { run_id: string; state: RunState; current_stage: string; created_at: string; duration_ms?: number; active_container?: string; latest_failure?: string }
export interface EventEnvelope { event_id: string; sequence: number; run_id: string; actor: EventActor; type: string; correlation_id: string; causation_id?: string | null; task_id?: string | null; ts: string; payload: Record<string, unknown>; meta?: Record<string, unknown> }
