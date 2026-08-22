import type { EventEnvelope, RunResponse } from '../generated/contracts';
import { CopyButton } from './CopyButton';
const stages: Record<string, string> = { RECEIVED: 'Execução recebida', WORKER_QUEUED: 'Worker na fila', WORKER_RUNNING: 'Worker em execução', COMPLETED: 'Execução concluída', FAILED: 'Execução falhou', CANCELED: 'Execução cancelada' };
const duration = (run: RunResponse) => { const ms = Math.max(0, Date.parse(run.updated_at) - Date.parse(run.created_at)); return `${Math.floor(ms / 60000)}m ${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}s`; };
export function RunSummary({ phase, run, events }: { phase: string; run: RunResponse; events: EventEnvelope[] }) {
  const latest = events[events.length - 1]; const transportError = phase === 'error';
  return <section className="summary card" aria-labelledby="summary-title"><div className="section-heading"><div><p className="eyebrow">EXECUCAO ATUAL</p><h2 id="summary-title">Resumo</h2></div><span className="pill">{transportError ? 'TRANSPORTE INDISPONIVEL' : run.state}</span></div>
    {phase === 'loading' && <p className="notice" role="status">Criando execução e carregando eventos…</p>}{transportError && <div className="error-panel" role="alert"><p>Falha de transporte: não foi possível consultar a execução.</p></div>}
    <div className="metrics"><div><span>Etapa atual</span><strong>{phase === 'loading' ? 'Aguardando resposta…' : transportError ? 'Consulta indisponível' : stages[run.state]}</strong></div><div><span>Duração</span><strong>{phase === 'loading' ? '—' : duration(run)}</strong></div><div><span>Última atualização</span><strong>{phase === 'loading' ? '—' : `${latest ? `Etapa ${latest.sequence}` : 'Nenhum evento'} · ${new Date(run.updated_at).toLocaleTimeString('pt-BR')}`}</strong></div><div><span>Container ativo</span><strong className="mono long">{phase === 'loading' ? '—' : latest?.meta.container_id ?? 'Nenhum'}</strong></div></div>
    <div className="identifiers"><span>Run ID <strong className="mono long">{run.run_id}</strong><CopyButton value={run.run_id} label="Run ID" /></span>{run.current_task_id && <span>Task ID <strong className="mono long">{run.current_task_id}</strong><CopyButton value={run.current_task_id} label="Task ID" /></span>}</div>
  </section>;
}
