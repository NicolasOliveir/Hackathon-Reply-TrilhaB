import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';
const briefing = 'Criar um painel de execução observável';
function submitBriefing() { fireEvent.change(screen.getByLabelText('O que você quer construir?'), { target: { value: briefing } }); fireEvent.click(screen.getByRole('button', { name: /iniciar/i })); }
describe('painel do orquestrador', () => {
  it('valida o briefing e preserva o texto', () => { render(<App />); const input = screen.getByLabelText('O que você quer construir?'); fireEvent.change(input, { target: { value: 'curto' } }); fireEvent.click(screen.getByRole('button', { name: /iniciar/i })); expect(screen.getByRole('alert')).toHaveTextContent('20 caracteres'); expect(input).toHaveValue('curto'); });
  it('expõe loading e impede envio duplicado', async () => { render(<App />); submitBriefing(); expect(screen.getByRole('status')).toHaveTextContent('carregando'); expect(screen.getByRole('button', { name: /execução enviada/i })).toBeDisabled(); await waitFor(() => expect(screen.getByText('BRIEFING RECEIVED')).toBeInTheDocument()); });
  it('ordena eventos por sequence e permite payload e reconexão', async () => { render(<App />); submitBriefing(); await waitFor(() => expect(screen.getAllByRole('button', { name: /ver payload/i })).toHaveLength(3)); fireEvent.click(screen.getAllByRole('button', { name: /ver payload/i })[2]); expect(screen.getByText(/manifest_hash/)).toBeInTheDocument(); fireEvent.click(screen.getByRole('button', { name: /simular reconexão/i })); expect(screen.getByText('Reconectando…')).toBeInTheDocument(); });
  it('mostra estado vazio ao limpar eventos', async () => { render(<App />); submitBriefing(); await waitFor(() => expect(screen.getByText('BRIEFING RECEIVED')).toBeInTheDocument()); fireEvent.click(screen.getByRole('button', { name: /limpar eventos/i })); expect(screen.getByText(/Ainda não há eventos/)).toBeInTheDocument(); });
  it('mostra erro operacional e permite tentar novamente', () => { render(<App />); fireEvent.click(screen.getByRole('button', { name: /simular erro/i })); expect(screen.getByRole('alert')).toHaveTextContent('Não foi possível'); expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument(); });
  it('mantém nomes acessíveis nos controles principais', () => { render(<App />); expect(screen.getByRole('textbox', { name: 'O que você quer construir?' })).toBeInTheDocument(); expect(screen.getByRole('button', { name: /iniciar execução/i })).toBeInTheDocument(); });
});
