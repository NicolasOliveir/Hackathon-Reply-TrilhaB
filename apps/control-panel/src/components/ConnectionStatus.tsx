export function ConnectionStatus({ state }: { state: 'connected' | 'reconnecting' | 'disconnected' }) {
  const label = state === 'connected' ? 'Atualização ativa' : state === 'reconnecting' ? 'Atualizando…' : 'Sem atualização';
  return <span className={`status status-${state}`} aria-live="polite"><i />{label}</span>;
}
