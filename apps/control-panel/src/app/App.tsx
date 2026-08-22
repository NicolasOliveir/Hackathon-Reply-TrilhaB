import { useEffect, useRef, useState } from 'react';
import type { ControlApi, ConnectionState } from '../api/controlApi';
import { controlApi } from '../api/controlApi';
import type { EventEnvelope, RunResponse } from '../generated/contracts';
import { ConnectionStatus } from '../components/ConnectionStatus';
import { EventTimeline } from '../components/EventTimeline';
import { RunForm } from '../components/RunForm';
import { RunSummary } from '../components/RunSummary';

type Phase = 'idle' | 'loading' | 'ready' | 'error';

function newIdempotencyKey(): string {
  return globalThis.crypto?.randomUUID?.() ??
    `panel-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function addEvent(current: EventEnvelope[], incoming: EventEnvelope): EventEnvelope[] {
  if (
    current.some(
      (event) =>
        event.event_id === incoming.event_id || event.sequence === incoming.sequence,
    )
  ) {
    return current;
  }
  return [...current, incoming].sort((left, right) => left.sequence - right.sequence);
}

export function App({ client = controlApi }: { client?: ControlApi }) {
  const [submitted, setSubmitted] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [connection, setConnection] = useState<ConnectionState>('disconnected');
  const [run, setRun] = useState<RunResponse | null>(null);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [error, setError] = useState('');
  const [reconnectVersion, setReconnectVersion] = useState(0);
  const lastBriefing = useRef('');
  const idempotencyKey = useRef('');
  const lastSequence = useRef(0);
  const submission = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      submission.current?.abort();
    },
    [],
  );

  useEffect(() => {
    if (!run) return;

    const controller = new AbortController();
    const activeRun = run;
    setConnection('reconnecting');

    void client
      .followRunEvents({
        url: activeRun.links.events,
        afterSequence: lastSequence.current,
        signal: controller.signal,
        onConnectionChange: setConnection,
        onEvent: (incoming) => {
          if (incoming.run_id !== activeRun.run_id) return;
          lastSequence.current = Math.max(lastSequence.current, incoming.sequence);
          setEvents((current) => addEvent(current, incoming));

          // Estado e timestamps continuam tendo uma única fonte de verdade no
          // backend; o painel não replica a máquina de estados a partir do tipo.
          void client
            .getRun(activeRun.links.self, controller.signal)
            .then((fresh) => {
              setRun((current) =>
                current?.run_id === fresh.run_id ? fresh : current,
              );
            })
            .catch(() => {
              // O SSE permanece responsável pela reconexão. Uma leitura de
              // resumo pode falhar sem apagar eventos já recebidos.
            });
        },
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setConnection('disconnected');
        setPhase('error');
        setError(
          reason instanceof Error
            ? `Falha de transporte: ${reason.message}`
            : 'Falha de transporte ao acompanhar a execução.',
        );
      });

    return () => controller.abort();
  }, [client, reconnectVersion, run?.links.events, run?.links.self, run?.run_id]);

  const submit = async (briefing: string) => {
    const normalized = briefing.trim();
    const isRetry = normalized === lastBriefing.current && idempotencyKey.current;
    lastBriefing.current = normalized;
    if (!isRetry) idempotencyKey.current = newIdempotencyKey();

    submission.current?.abort();
    const controller = new AbortController();
    submission.current = controller;
    setSubmitted(true);
    setPhase('loading');
    setConnection('reconnecting');
    setError('');

    try {
      const created = await client.createRun(
        normalized,
        idempotencyKey.current,
        controller.signal,
      );
      lastSequence.current = 0;
      setEvents([]);
      setRun(created);
      setPhase('ready');
    } catch (reason) {
      if (controller.signal.aborted) return;
      setRun(null);
      setConnection('disconnected');
      setPhase('error');
      setError(
        reason instanceof Error
          ? `Falha de transporte: ${reason.message}`
          : 'Falha de transporte ao criar a execução.',
      );
    }
  };

  const simulateError = (briefing: string) => {
    submission.current?.abort();
    lastBriefing.current = briefing.trim();
    setSubmitted(true);
    setRun(null);
    setConnection('disconnected');
    setPhase('error');
    setError('Falha de transporte: não foi possível consultar a execução.');
  };

  const retry = () => {
    if (lastBriefing.current) {
      void submit(lastBriefing.current);
      return;
    }
    setSubmitted(false);
    setPhase('idle');
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">CONTROL PLANE</p>
          <h1>Orquestrador</h1>
        </div>
        <ConnectionStatus state={connection} />
      </header>

      {!submitted ? (
        <RunForm onSubmit={submit} onError={simulateError} />
      ) : !run ? (
        <section className="summary card" aria-labelledby="request-status-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">EXECUCAO ATUAL</p>
              <h2 id="request-status-title">Resumo</h2>
            </div>
          </div>
          {phase === 'loading' ? (
            <p className="notice" role="status">
              Criando execução e conectando à linha do tempo…
            </p>
          ) : (
            <div className="error-panel" role="alert">
              <p>{error}</p>
            </div>
          )}
          {phase === 'error' && (
            <button className="retry" onClick={retry}>
              Tentar novamente
            </button>
          )}
        </section>
      ) : (
        <>
          <RunSummary phase={phase} run={run} events={events} />
          {phase === 'error' && (
            <button
              className="retry"
              onClick={() => setReconnectVersion((value) => value + 1)}
            >
              Tentar novamente
            </button>
          )}
          <EventTimeline
            events={events}
            connection={connection}
            onReconnect={() => setReconnectVersion((value) => value + 1)}
          />
        </>
      )}
    </main>
  );
}
