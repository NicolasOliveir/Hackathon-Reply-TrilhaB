import type { EventEnvelope, RunResponse } from '../generated/contracts';

const CONTRACT_VERSION = '1.0.0';
const MAX_RECONNECT_DELAY_MS = 5_000;

export type ConnectionState = 'connected' | 'reconnecting' | 'disconnected';
export type BacklogStory = { story_id: string; title: string; narrative: string; priority: string; ready: boolean; acceptance_criteria: { criterion_id: string; description: string }[] };
export type BacklogResponse = { product_goal: string; stories: BacklogStory[] };

export type FollowRunEventsOptions = {
  url: string;
  afterSequence: number;
  signal: AbortSignal;
  onEvent: (event: EventEnvelope) => void;
  onConnectionChange: (state: ConnectionState) => void;
};

export type ControlApi = {
  createRun: (
    briefing: string,
    idempotencyKey: string,
    signal?: AbortSignal,
  ) => Promise<RunResponse>;
  getRun: (url: string, signal?: AbortSignal) => Promise<RunResponse>;
  getBacklog: (runId: string, signal?: AbortSignal) => Promise<BacklogResponse>;
  followRunEvents: (options: FollowRunEventsOptions) => Promise<void>;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function configuredApiBase(): string {
  const configured = import.meta.env.VITE_CONTROL_API_URL?.trim();
  if (configured) return configured.replace(/\/$/, '');

  // Em acesso mobile, `localhost` apontaria para o telefone. Reutilizar o host
  // da página faz 192.168.x.x:5173 conversar com 192.168.x.x:8000 por padrão.
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

function apiUrl(resource: string): string {
  const base = configuredApiBase();
  const parsed = new URL(resource, `${base}/`);
  return `${base}${parsed.pathname}${parsed.search}`;
}

async function responseError(response: Response): Promise<ApiError> {
  let detail = `A API respondeu com status ${response.status}.`;
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === 'string') detail = payload.detail;
  } catch {
    // Respostas de proxy podem não ser JSON; o status ainda é informativo.
  }
  return new ApiError(detail, response.status);
}

async function requestRun(url: string, init: RequestInit): Promise<RunResponse> {
  const response = await fetch(apiUrl(url), init);
  if (!response.ok) throw await responseError(response);
  return (await response.json()) as RunResponse;
}

export function parseSseFrame(frame: string): EventEnvelope | null {
  const lines = frame.replace(/\r\n?/g, '\n').split('\n');
  let id: number | undefined;
  const data: string[] = [];

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const rawValue = separator === -1 ? '' : line.slice(separator + 1);
    const value = rawValue.startsWith(' ') ? rawValue.slice(1) : rawValue;
    if (field === 'id') id = Number(value);
    if (field === 'data') data.push(value);
  }

  if (data.length === 0) return null;
  const event = JSON.parse(data.join('\n')) as EventEnvelope;
  if (
    !Number.isInteger(id) ||
    !Number.isInteger(event.sequence) ||
    event.sequence < 1 ||
    event.sequence !== id ||
    event.contract_version !== CONTRACT_VERSION ||
    typeof event.event_id !== 'string' ||
    typeof event.run_id !== 'string'
  ) {
    throw new ApiError('Evento SSE incompatível com o contrato versionado.');
  }
  return event;
}

type StreamCallbacks = Pick<
  FollowRunEventsOptions,
  'signal' | 'onEvent' | 'onConnectionChange'
>;

export async function consumeEventStream(
  resource: string,
  afterSequence: number,
  callbacks: StreamCallbacks,
): Promise<number> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  if (afterSequence > 0) headers['Last-Event-ID'] = String(afterSequence);

  const response = await fetch(apiUrl(resource), {
    method: 'GET',
    headers,
    signal: callbacks.signal,
  });
  if (!response.ok) throw await responseError(response);
  if (!response.body) throw new ApiError('A resposta SSE não possui um stream legível.');
  if (!response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new ApiError('A API não respondeu com text/event-stream.');
  }

  callbacks.onConnectionChange('connected');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let cursor = afterSequence;
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseFrame(frame);
        if (event && event.sequence > cursor) {
          cursor = event.sequence;
          callbacks.onEvent(event);
        }
        boundary = buffer.indexOf('\n\n');
      }

      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }

  return cursor;
}

function waitForRetry(delayMs: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const onAbort = () => {
      window.clearTimeout(timeout);
      reject(signal.reason);
    };
    const timeout = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, delayMs);
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export const controlApi: ControlApi = {
  createRun(briefing, idempotencyKey, signal) {
    return requestRun('/api/v1/runs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ contract_version: CONTRACT_VERSION, briefing }),
      signal,
    });
  },

  getRun(url, signal) {
    return requestRun(url, { method: 'GET', signal });
  },

  async getBacklog(runId, signal) {
    const response = await fetch(apiUrl(`/api/v1/runs/${runId}/backlog`), { signal });
    if (!response.ok) throw await responseError(response);
    return (await response.json()) as BacklogResponse;
  },

  async followRunEvents(options) {
    let cursor = options.afterSequence;
    let retry = 0;

    while (!options.signal.aborted) {
      try {
        cursor = await consumeEventStream(options.url, cursor, options);
        retry = 0;
      } catch (error) {
        if (options.signal.aborted) return;
        // Falha de transporte e EOF usam a mesma retomada pelo último cursor.
        if (error instanceof ApiError && error.status === 404) throw error;
      }

      if (options.signal.aborted) return;
      options.onConnectionChange('reconnecting');
      const delay = Math.min(250 * 2 ** retry, MAX_RECONNECT_DELAY_MS);
      retry += 1;
      try {
        await waitForRetry(delay, options.signal);
      } catch {
        return;
      }
    }
  },
};
