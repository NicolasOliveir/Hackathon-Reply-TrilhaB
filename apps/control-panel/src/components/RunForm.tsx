import { useState } from 'react';
export function RunForm({ onSubmit, onError }: { onSubmit: (value: string) => void; onError: () => void }) {
  const [value, setValue] = useState(''); const [error, setError] = useState('');
  const submit = (event: React.FormEvent) => { event.preventDefault(); if (value.trim().length < 20) { setError('Descreva o objetivo com pelo menos 20 caracteres.'); return; } setError(''); onSubmit(value); };
  return <section className="hero"><p className="eyebrow">FATIA 1 · OBSERVABILIDADE</p><h2>Briefing para execução</h2><p className="muted">Envie uma vez e acompanhe cada decisão do fluxo.</p>
    <form onSubmit={submit} noValidate><label htmlFor="briefing">O que você quer construir?</label><textarea id="briefing" value={value} onChange={(event) => { setValue(event.target.value); setError(''); }} aria-invalid={Boolean(error)} aria-describedby={error ? 'briefing-error' : 'briefing-help'} placeholder="Ex.: Criar uma tela de cadastro com validação…" /><p id="briefing-help" className="hint">O texto é preservado se houver erro.</p>{error && <p id="briefing-error" className="error" role="alert">{error}</p>}<button type="submit">Iniciar execução <span aria-hidden>→</span></button><button type="button" className="secondary demo-error" onClick={onError}>Simular erro</button></form>
  </section>;
}
