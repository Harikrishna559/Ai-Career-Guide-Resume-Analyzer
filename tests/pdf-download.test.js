const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const window = {};
const document = { addEventListener() {} };
const source = fs.readFileSync(path.join(__dirname, '..', 'public', 'static', 'js', 'main.js'), 'utf8');
vm.runInNewContext(source, { window, document });

test('PDF response reader returns a blob only for a successful PDF response', async () => {
  const expectedBlob = { kind: 'pdf' };
  const blob = await window.readPdfResponse({
    ok: true,
    headers: { get: () => 'application/pdf; charset=binary' },
    blob: async () => expectedBlob,
  }, 'fallback');

  assert.equal(blob, expectedBlob);
});

test('PDF response reader surfaces JSON errors without reading them as blobs', async () => {
  let blobRead = false;
  await assert.rejects(
    window.readPdfResponse({
      ok: false,
      headers: { get: () => 'application/json' },
      json: async () => ({ success: false, error: { message: 'Report request too large.' } }),
      blob: async () => {
        blobRead = true;
        return {};
      },
    }, 'fallback'),
    /Report request too large/,
  );
  assert.equal(blobRead, false);
});

test('PDF response reader rejects a non-PDF success response', async () => {
  await assert.rejects(
    window.readPdfResponse({
      ok: true,
      headers: { get: () => 'application/json' },
      blob: async () => ({}),
    }, 'fallback'),
    /invalid report file/,
  );
});
