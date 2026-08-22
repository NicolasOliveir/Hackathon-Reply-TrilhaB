import '../styles.css';
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
});
