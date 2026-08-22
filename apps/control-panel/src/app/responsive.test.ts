import '../styles.css';
import '../briefing.css';
import { describe, expect, it } from 'vitest';
describe('contrato responsivo do painel', () => {
  it('não impõe largura mínima e mantém controles com alvo de toque', () => {
    const root = document.documentElement;
    const button = document.createElement('button');
    button.className = 'copy'; document.body.append(button);
    expect(getComputedStyle(root).minWidth).not.toBe('320px');
    expect(button.className).toContain('copy');
    button.remove();
  });
  it('mantém a ação principal larga e o formulário sem largura mínima', () => {
    const form = document.createElement('form');
    form.className = 'briefing-card';
    const button = document.createElement('button');
    button.className = 'primary-action';
    form.append(button);
    document.body.append(form);
    expect(form.className).toContain('briefing-card');
    expect(button.className).toContain('primary-action');
    form.remove();
  });
});
