import { useState } from 'react';
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard?.writeText(value); } catch {
      const textarea = document.createElement('textarea'); textarea.value = value; document.body.appendChild(textarea); textarea.select(); document.execCommand('copy'); textarea.remove();
    }
    setCopied(true); window.setTimeout(() => setCopied(false), 1500);
  };
  return <><button className="copy" onClick={copy} aria-label={`${label}: copiar`}>{copied ? 'Copiado' : 'Copiar'}</button><span className="sr-only" aria-live="polite">{copied ? `${label} copiado` : ''}</span></>;
}
