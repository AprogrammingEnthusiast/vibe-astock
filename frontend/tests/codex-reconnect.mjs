import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the actual Settings component across device-login polling renders.
let cursor = 0, dirty = false, tree, interval;
const cells = [], effects = [];
const react = {
  useState(initial) {
    const i = cursor++;
    if (!(i in cells)) cells[i] = typeof initial === 'function' ? initial() : initial;
    return [cells[i], next => { const value = typeof next === 'function' ? next(cells[i]) : next; if (!Object.is(value, cells[i])) { cells[i] = value; dirty = true; } }];
  },
  useRef(initial) { return react.useState(() => ({ current: initial }))[0]; },
  useEffect(fn, deps) {
    const i = cursor++, old = cells[i];
    if (!old || deps.some((v, n) => !Object.is(v, old.deps[n]))) {
      cells[i] = { deps }; effects.push(() => { old?.cleanup?.(); cells[i].cleanup = fn(); });
    }
  },
};
const jsx = (type, props) => ({ type, props: props || {} });
let status = { kind: 'codex', allowed: true, installed: true, authenticated: false, status: 'logged_out' };
let saved;
const codex = { id: 'codex', provider: 'cli-codex', name: 'Codex' };
const api = { id: 'custom', provider: 'openai-compatible' };
const models = {
  subscriptionModels: [codex], apiModels: [api], aiModels: [codex, api], PROVIDER_BASE: {},
  isCliProvider: p => p.startsWith('cli-'), cliKindOf: p => p.slice(4),
  cliAvailability: () => ({ clis: [status] }), cliAvailState: () => 'ready',
  primeCliAvailability: async () => ({ clis: [status] }),
  startCodexDeviceAuth: async () => { status = { ...status, status: 'login_pending' }; },
};
const modules = {
  react, 'react/jsx-runtime': { jsx, jsxs: jsx },
  'lucide-react': new Proxy({}, { get: (_, key) => String(key) }),
  '@/lib/account': { sharedWebsite: true },
  '@/lib/llm': { loadLlm: () => saved || null, staleBlockedProvider: () => null, saveLlm: async value => { saved = value; } },
  '@/lib/api': { authHeaders: () => ({}), loadAccessKey: () => '' },
  '@/lib/ai-models': models,
  sonner: { toast: { success() {}, error(message) { throw new Error(message); } } },
};
const exports = {};
vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/pages/Settings.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText, { exports, require: name => modules[name] || new Proxy({}, { get: (_, key) => String(key) }),
  window: { setInterval: fn => { interval = fn; return 1; }, clearInterval: () => { interval = null; } },
});
const nodes = node => !node || typeof node !== 'object' ? [] : Array.isArray(node)
  ? node.flatMap(nodes) : [node, ...nodes(node.props?.children)];
const textOf = node => !node || typeof node === 'boolean' ? '' : typeof node !== 'object' ? String(node)
  : Array.isArray(node) ? node.map(textOf).join('') : textOf(node.props?.children);
async function render() {
  for (let n = 0; n < 20; n++) {
    dirty = false; cursor = 0; tree = exports.Settings();
    effects.splice(0).forEach(fn => fn()); await new Promise(resolve => setImmediate(resolve));
    if (!dirty) return;
  }
  throw new Error('Settings render did not settle');
}
await render();
nodes(tree).find(n => n.props.onClick && textOf(n).startsWith('订阅接入')).props.onClick();
await render();
await nodes(tree).find(n => n.type === 'button' && textOf(n) === '登录 Codex').props.onClick();
await render();
assert.ok(interval, 'Device authorization must be polled');
status = { ...status, authenticated: true, status: 'ready', models: ['model-a', 'model-b'], model: 'model-a' };
await interval(); await render();
const picker = nodes(tree).find(n => n.type === 'select' && n.props.id === 'codex-model');
assert.ok(picker, 'After reconnect, model selection must appear without clicking Codex again');
assert.ok(nodes(tree).some(n => n.type === 'dialog'), 'Successful reconnect must open model selection');
picker.props.onChange({ target: { value: 'model-b' } }); await render();
await nodes(tree).find(n => n.type === 'button' && textOf(n) === '保存并完成连接').props.onClick();
await render();
assert.equal(saved.provider, 'cli-codex'); assert.equal(saved.model, 'model-b');
assert.ok(!nodes(tree).some(n => n.type === 'dialog'), 'Save closes model selection');
console.log('Codex reconnect → model selection → personal configuration save passed.');
