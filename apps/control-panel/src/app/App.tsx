import { useState } from 'react';
import type { EventEnvelope } from '../generated/contracts';
import { mockEvents, mockRun } from '../mocks/orchestrator';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { RunForm } from '../components/RunForm';
import { RunSummary } from '../components/RunSummary';
import { EventTimeline } from '../components/EventTimeline';

export function App() {
  const [submitted, setSubmitted] = useState(false);
  const [phase, setPhase] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [connection, setConnection] = useState<'connected' | 'reconnecting' | 'disconnected'>('connected');
  const [events, setEvents] = useState<EventEnvelope[]>([]);

  const loadMock = () => {
    setPhase('loading');
    window.setTimeout(() => { setEvents([...mockEvents]); setPhase('ready'); }, 250);
  };
  const submit = () => { setSubmitted(true); loadMock(); };
  const retry = () => loadMock();
  const addFailureDemo = () => setEvents((current) => [...current, {
    ...mockEvents[3], event_id: '3b6b4c9e-8d01-4a01-9a11-100000000005', sequence: 5,
    type: 'AGENT_FAILED', causation_id: mockEvents[3].event_id,
    ts: '2026-08-22T16:00:08.000Z', payload: { summary: 'Agente não conseguiu concluir a tarefa', error_code: 'WORKER_TIMEOUT' },
  }]);
  return <main className="shell">
    <header className="topbar"><div><p className="eyebrow">CONTROL PLANE</p><h1>Orquestrador</h1></div><ConnectionStatus state={connection} /></header>
    {!submitted ? <RunForm onSubmit={submit} onError={() => { setSubmitted(true); setPhase('error'); }} /> : <>
      <RunSummary phase={phase} run={mockRun} events={events} />
      {phase === 'error' && <button className="retry" onClick={retry}>Tentar novamente</button>}
      <EventTimeline events={events} connection={connection}
        onReconnect={() => setConnection((state) => state === 'connected' ? 'reconnecting' : 'connected')}
        onFailureDemo={addFailureDemo} />
    </>}
  </main>;
}
