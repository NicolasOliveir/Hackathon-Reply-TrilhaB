export function ConnectionStatus({ state }: { state: 'connected' | 'reconnecting' | 'disconnected' }) {
  const label = state === 'connected' ? 'Conectado' : state === 'reconnecting' ? 'Reconectando…' : 'Desconectado';
  return <span className={`status status-${state}`} aria-live="polite"><i />{label}</span>;
}
