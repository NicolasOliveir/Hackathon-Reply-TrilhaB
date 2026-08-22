import { useRef, useState } from 'react';

const MIN_BRIEFING_LENGTH = 30;
const EXAMPLE_BRIEFING =
  'Precisamos registrar não conformidades pelo celular, anexar evidências e acompanhar quem ficou responsável por cada ação.';

type RunFormProps = {
  onSubmit: (value: string) => void;
  onError: (value: string) => void;
};

export function RunForm({ onSubmit, onError }: RunFormProps) {
  const [value, setValue] = useState('');
  const [error, setError] = useState('');
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const remaining = Math.max(0, MIN_BRIEFING_LENGTH - value.trim().length);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (remaining > 0) {
      setError(`Conte um pouco mais para podermos ajudar. Faltam ${remaining} caracteres.`);
      fieldRef.current?.focus();
      return;
    }
    setError('');
    onSubmit(value.trim());
  };

  const useExample = () => {
    setValue(EXAMPLE_BRIEFING);
    setError('');
    fieldRef.current?.focus();
  };

  return (
    <section className="briefing-page" aria-labelledby="briefing-title">
      <div className="briefing-intro">
        <span className="step-badge">Conte sua ideia</span>
        <h2 id="briefing-title">Que solução você quer criar?</h2>
        <p className="briefing-lead">
          Explique o problema do seu jeito. Nós cuidamos da parte técnica.
        </p>
      </div>

      <form className="briefing-card" onSubmit={submit} noValidate>
        <div className="field-heading">
          <label htmlFor="briefing">Conte o que a aplicação precisa fazer</label>
          <span className={remaining > 0 ? 'character-count' : 'character-count complete'} aria-live="polite">
            {remaining > 0 ? `Faltam ${remaining}` : 'Descrição suficiente'}
          </span>
        </div>
        <textarea
          ref={fieldRef}
          id="briefing"
          value={value}
          onChange={(event) => { setValue(event.target.value); setError(''); }}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? 'briefing-error briefing-help' : 'briefing-help'}
          placeholder="Ex.: Hoje anotamos os problemas em papel e não conseguimos acompanhar o que já foi resolvido…"
          rows={7}
        />
        <div className="field-support">
          <p id="briefing-help">Você poderá acompanhar cada etapa depois do envio.</p>
          <button type="button" className="example-action" onClick={useExample}>Usar um exemplo</button>
        </div>
        {error && <p id="briefing-error" className="form-error" role="alert">{error}</p>}
        <div className="submit-area">
          <button type="submit" className="primary-action">Começar a criar <span aria-hidden="true">→</span></button>
          <p><span aria-hidden="true">✓</span> Você acompanhará o progresso nesta tela.</p>
        </div>
        <details className="demo-tools">
        <summary>Recursos para demonstração</summary>
          <button type="button" className="secondary" onClick={() => onError(value)}>Simular erro de conexão</button>
        </details>
      </form>

      <details className="prompt-guide">
        <summary>Precisa de ajuda para escrever?</summary>
        <p>Inclua estas informações:</p>
        <ul>
          <li><span aria-hidden="true">1</span> Qual problema acontece hoje?</li>
          <li><span aria-hidden="true">2</span> Quem é afetado por ele?</li>
          <li><span aria-hidden="true">3</span> Como seria uma solução útil?</li>
        </ul>
      </details>
    </section>
  );
}
