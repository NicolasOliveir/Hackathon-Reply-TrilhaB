import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ControlApi, FollowRunEventsOptions } from '../api/controlApi';
import { mockEvents, mockRun } from '../mocks/orchestrator';
import { App } from './App';

const label = 'Descreva sua necessidade';
const validBriefing = 'Criar um painel de execução observável pelo celular';

function waitUntilAbort(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) resolve();
    else signal.addEventListener('abort', () => resolve(), { once: true });
  });
}

function testClient(overrides: Partial<ControlApi> = {}): ControlApi {
  return {
    createRun: vi.fn(async () => mockRun),
    getRun: vi.fn(async () => mockRun),
    followRunEvents: vi.fn(async (options: FollowRunEventsOptions) => {
      options.onConnectionChange('connected');
      mockEvents.forEach(options.onEvent);
      await waitUntilAbort(options.signal);
    }),
    ...overrides,
  };
}

function submit() {
  fireEvent.change(screen.getByLabelText(label), {
    target: { value: validBriefing },
  });
  fireEvent.click(screen.getByRole('button', { name: /enviar e acompanhar/i }));
}

describe('painel responsivo e auditoria', () => {
  it('valida, preserva e foca um briefing curto', () => {
    render(<App client={testClient()} />);
    const field = screen.getByLabelText(label);
    fireEvent.change(field, { target: { value: 'curto' } });
    fireEvent.click(screen.getByRole('button', { name: /enviar e acompanhar/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Conte um pouco mais');
    expect(field).toHaveValue('curto');
    expect(field).toHaveFocus();
  });

  it('orienta uma pessoa não técnica e oferece exemplo preenchível', () => {
    render(<App client={testClient()} />);
    expect(screen.getByRole('heading', { name: /precisa melhorar no trabalho/i })).toBeInTheDocument();
    expect(screen.getByText(/não precisa usar termos técnicos/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /usar um exemplo/i }));
    expect((screen.getByLabelText(label) as HTMLTextAreaElement).value).toContain('não conformidades');
  });

  it('cria um run real e carrega eventos tipados', async () => {
    const client = testClient();
    render(<App client={client} />);
    submit();

    expect(screen.getByRole('status')).toHaveTextContent('Criando execução');
    await waitFor(() => expect(screen.getByText('Briefing recebido')).toBeInTheDocument());
    expect(client.createRun).toHaveBeenCalledWith(
      validBriefing,
      expect.stringMatching(/^.{8,}$/),
      expect.any(AbortSignal),
    );
    expect(client.getRun).toHaveBeenCalled();
  });

  it('expõe sequência, causalidade, IDs e detalhes progressivos', async () => {
    render(<App client={testClient()} />);
    submit();
    await waitFor(() => expect(screen.getByText('Briefing recebido')).toBeInTheDocument());
    expect(screen.getByText('Etapa 2')).toBeInTheDocument();
    fireEvent.click(screen.getAllByText(/Detalhes t/)[0]);
    expect(screen.getAllByText(/Correlation ID/).length).toBeGreaterThan(0);
  });

  it('filtra e limpa auditoria', async () => {
    render(<App client={testClient()} />);
    submit();
    await waitFor(() => expect(screen.getByText('Briefing recebido')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Sistema' }));
    expect(screen.getAllByText(/Execu/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: 'Limpar filtros' }));
    expect(screen.getByText('Briefing recebido')).toBeInTheDocument();
  });

  it('distingue erro de transporte e permite tentar novamente', () => {
    render(<App client={testClient()} />);
    fireEvent.click(screen.getByRole('button', { name: /simular erro/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Falha de transporte');
    expect(screen.getByRole('button', { name: /tentar/i })).toBeInTheDocument();
  });

  it('reutiliza a chave idempotente ao repetir uma criação que falhou', async () => {
    const createRun = vi
      .fn<ControlApi['createRun']>()
      .mockRejectedValueOnce(new Error('rede indisponível'))
      .mockResolvedValueOnce(mockRun);
    const client = testClient({ createRun });
    render(<App client={client} />);
    submit();

    await screen.findByText(/rede indisponível/i);
    const firstKey = createRun.mock.calls[0][1];
    fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    await screen.findByText('Briefing recebido');

    expect(createRun).toHaveBeenCalledTimes(2);
    expect(createRun.mock.calls[1][1]).toBe(firstKey);
  });

  it('reconecta do último sequence e não duplica eventos visíveis', async () => {
    const followRunEvents = vi.fn(async (options: FollowRunEventsOptions) => {
      options.onConnectionChange('connected');
      mockEvents.forEach(options.onEvent);
      await waitUntilAbort(options.signal);
    });
    const client = testClient({ followRunEvents });
    const { container } = render(<App client={client} />);
    submit();

    await waitFor(() => expect(container.querySelectorAll('.timeline li')).toHaveLength(4));
    fireEvent.click(screen.getByRole('button', { name: /reconectar agora/i }));
    await waitFor(() => expect(followRunEvents).toHaveBeenCalledTimes(2));

    expect(followRunEvents.mock.calls[1][0].afterSequence).toBe(4);
    expect(container.querySelectorAll('.timeline li')).toHaveLength(4);
  });

  it('não renderiza marcadores de encoding corrompido em ready e error', async () => {
    const { unmount } = render(<App client={testClient()} />);
    submit();
    await waitFor(() => expect(screen.getByText('Briefing recebido')).toBeInTheDocument());
    expect(document.body.textContent).not.toMatch(/\u00c3|\u00c2|\ufffd/);
    unmount();
    render(<App client={testClient()} />);
    fireEvent.click(screen.getByRole('button', { name: /simular erro/i }));
    expect(document.body.textContent).not.toMatch(/\u00c3|\u00c2|\ufffd/);
  });

  it('anuncia feedback de cópia e mantém causa na camada principal', async () => {
    render(<App client={testClient()} />);
    submit();
    await waitFor(() => expect(screen.getByText('Briefing recebido')).toBeInTheDocument());
    expect(screen.getAllByText(/Causado pela/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: /Run ID: copiar/i })[0]);
    expect(await screen.findByText(/Run ID copiado/)).toBeInTheDocument();
  });
});
