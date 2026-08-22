import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockEvents } from '../mocks/orchestrator';
import { consumeEventStream, parseSseFrame } from './controlApi';

afterEach(() => vi.unstubAllGlobals());

describe('cliente SSE', () => {
  it('interpreta o id como sequence e preserva o envelope', () => {
    const event = mockEvents[1];
    const parsed = parseSseFrame(`id: ${event.sequence}\ndata: ${JSON.stringify(event)}`);

    expect(parsed).toEqual(event);
  });

  it('ignora heartbeat e campos SSE desconhecidos', () => {
    expect(parseSseFrame(': keep-alive')).toBeNull();
    expect(parseSseFrame('retry: 1000')).toBeNull();
  });

  it('recusa divergência entre id SSE e sequence do contrato', () => {
    expect(() =>
      parseSseFrame(`id: 99\ndata: ${JSON.stringify(mockEvents[0])}`),
    ).toThrow(/incompatível/);
  });

  it('envia Last-Event-ID e ignora evento repetido após reconexão', async () => {
    const second = `id: 2\ndata: ${JSON.stringify(mockEvents[1])}\n\n`;
    const third = `id: 3\ndata: ${JSON.stringify(mockEvents[2])}\n\n`;
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(second.slice(0, 17)));
        controller.enqueue(encoder.encode(second.slice(17) + second + third));
        controller.close();
      },
    });
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(body, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const received: number[] = [];

    const cursor = await consumeEventStream('/api/v1/runs/run-1/events', 1, {
      signal: new AbortController().signal,
      onConnectionChange: vi.fn(),
      onEvent: (event) => received.push(event.sequence),
    });

    expect(received).toEqual([2, 3]);
    expect(cursor).toBe(3);
    const request = fetchMock.mock.calls[0];
    expect(String(request[0])).toContain('localhost:8000/api/v1/runs/run-1/events');
    expect(request[1]?.headers).toMatchObject({ 'Last-Event-ID': '1' });
  });
});
