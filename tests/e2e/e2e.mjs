import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const panelUrl = process.env.E2E_PANEL_URL ?? 'http://control-panel';
const apiUrl = (process.env.E2E_API_URL ?? 'http://control-api:8000').replace(/\/$/, '');
const expectedTypes = [
  'RUN_CREATED',
  'BRIEFING_RECEIVED',
  'TASK_QUEUED',
  'AGENT_STARTED',
  'FAKE_WORKER_COMPLETED',
  'RUN_COMPLETED',
];

function apiResource(resource) {
  const parsed = new URL(resource, `${apiUrl}/`);
  return `${apiUrl}${parsed.pathname}${parsed.search}`;
}

function parseFrame(frame) {
  const lines = frame.replace(/\r\n?/g, '\n').split('\n');
  const data = [];
  let id;
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    const value = separator === -1 ? '' : line.slice(separator + 1).trimStart();
    if (field === 'id') id = Number(value);
    if (field === 'data') data.push(value);
  }
  if (data.length === 0) return null;
  const event = JSON.parse(data.join('\n'));
  assert.equal(event.sequence, id, 'o id SSE deve ser o sequence do evento');
  return event;
}

async function readUntilCompleted(resource, afterSequence) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  const headers = { Accept: 'text/event-stream' };
  if (afterSequence > 0) headers['Last-Event-ID'] = String(afterSequence);

  try {
    const response = await fetch(apiResource(resource), {
      headers,
      signal: controller.signal,
    });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type') ?? '', /text\/event-stream/);
    assert.ok(response.body);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    const events = [];
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const event = parseFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (event) {
          events.push(event);
          if (event.type === 'RUN_COMPLETED') {
            await reader.cancel();
            return events;
          }
        }
        boundary = buffer.indexOf('\n\n');
      }
      if (done) throw new Error('stream SSE terminou antes de RUN_COMPLETED');
    }
  } finally {
    clearTimeout(timeout);
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  try {
    await page.goto(panelUrl, { waitUntil: 'networkidle' });
    await page.getByRole('heading', {
      name: /o que você precisa melhorar no trabalho/i,
    }).waitFor();

    const briefing =
      'Validar pelo celular a fatia distribuída, a causalidade e o isolamento do fake worker.';
    const createdResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        response.url().endsWith('/api/v1/runs'),
    );

    await page.getByLabel('Descreva sua necessidade').fill(briefing);
    await page.getByRole('button', { name: /enviar e acompanhar/i }).click();

    const createdResponse = await createdResponsePromise;
    assert.equal(createdResponse.status(), 202);
    const created = await createdResponse.json();
    const requestHeaders = await createdResponse.request().allHeaders();
    const idempotencyKey = requestHeaders['idempotency-key'];
    assert.ok(idempotencyKey, 'o painel deve enviar Idempotency-Key');

    const replayResponse = await fetch(`${apiUrl}/api/v1/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify({ contract_version: '1.0.0', briefing }),
    });
    assert.equal(replayResponse.status, 202);
    const replay = await replayResponse.json();
    assert.equal(replay.run_id, created.run_id, 'retry não pode criar outro run');

    await page
      .locator('.timeline .event-meta > span:first-child', {
        hasText: 'RUN_COMPLETED',
      })
      .waitFor({ timeout: 45_000 });
    await page.locator('.summary .pill', { hasText: 'COMPLETED' }).waitFor();

    const timelineTypes = await page
      .locator('.timeline .event-meta > span:first-child')
      .allTextContents();
    assert.deepEqual(timelineTypes, expectedTypes);
    assert.equal(
      timelineTypes.filter((type) => type === 'AGENT_STARTED').length,
      1,
      'retry não pode iniciar outro container',
    );

    const causality = await page.locator('.timeline .causality').allTextContents();
    assert.match(causality[0], /Origem da execução/);
    for (const description of causality.slice(1)) {
      assert.match(description, /Causado pela/, 'a timeline deve encadear cada efeito');
    }

    const summaryText = await page.locator('.summary').innerText();
    assert.match(summaryText, new RegExp(created.run_id));
    assert.match(summaryText, /Execução concluída/);

    const resumed = await readUntilCompleted(created.links.events, 3);
    assert.deepEqual(
      resumed.map((event) => event.sequence),
      [4, 5, 6],
      'retomada SSE deve ser exclusiva e sem duplicação',
    );
    assert.deepEqual(resumed.map((event) => event.type), expectedTypes.slice(3));
    assert.ok(resumed.every((event) => event.correlation_id === created.run_id));

    const currentResponse = await fetch(`${apiUrl}/api/v1/runs/${created.run_id}`);
    assert.equal(currentResponse.status, 200);
    const current = await currentResponse.json();
    assert.equal(current.state, 'COMPLETED');

    console.log(
      JSON.stringify(
        {
          result: 'PASS',
          run_id: created.run_id,
          task_id: created.current_task_id,
          final_state: current.state,
          timeline: timelineTypes,
          resumed_sequences: resumed.map((event) => event.sequence),
          idempotent_retry_run_id: replay.run_id,
          viewport: '390x844',
        },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
  }
}

await run();
