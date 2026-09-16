import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';

// Run the component's actual ranking and ECharts options without a DOM.
const source = readFileSync(new URL('../src/components/SectorFlowPanel.tsx', import.meta.url), 'utf8');
const start = source.indexOf('  const sectorTreemapRows');
const end = source.indexOf('  useEffect', start);
const js = ts.transpile(source.slice(start, end), { target: ts.ScriptTarget.ES2022 });
const options = (sectors, direction = "all") => vm.runInNewContext(`${js}\nsectorTreemapOption`, {
  direction, overview: { sectors }, useMemo: (fn) => fn(), fmt: (n) => String(n),
});
const sectors = [
  { name: 'out', net: -100, pct: -2 }, { name: 'in', net: 50, pct: 1 },
  ...[0, null, undefined, NaN, Infinity].map((net) => ({ name: 'invalid', net })),
  ...Array.from({ length: 20 }, (_, i) => ({ name: `small-${i}`, net: i + 1 })),
];
const option = options(sectors);
const rows = option.series[0].data;
assert.equal(rows.length, 15);
assert.equal(rows[0].name, 'out');
assert.equal(rows[0].value, 100);
assert.equal(rows[1].name, 'in');
assert.ok(rows.every((row) => Number.isFinite(row.value) && row.value > 0));
assert.notEqual(rows[0].itemStyle.color, rows[1].itemStyle.color);
assert.match(option.tooltip.formatter({ data: rows[0] }), /净流出：-100/);
assert.match(option.tooltip.formatter({ data: rows[1] }), /净流入：\+50/);
assert.equal(options([]).series[0].data.length, 0);
assert.equal(sectors[0].name, 'out');
console.log('Sector flow ranking, direction, missing data and tooltip checks passed.');

const mixed = Array.from({ length: 40 }, (_, i) => ({ name: `sector-${i}`, net: i % 2 ? -(i + 1) : i + 1 }));
for (const direction of ['in', 'out']) {
  const filtered = options(mixed, direction).series[0].data;
  assert.equal(filtered.length, 15);
  assert.ok(filtered.every((r) => direction === 'in' ? r.net > 0 : r.net < 0));
  assert.equal(filtered[0].value, direction === 'in' ? 39 : 40);
  assert.equal(filtered.at(-1).value, direction === 'in' ? 11 : 12);
}
assert.equal(options([{ name: 'only-in', net: 1 }], 'out').series[0].data.length, 0);
assert.equal(options([{ name: 'only-in', net: 1 }], 'in').series[0].data.length, 1);
console.log('Direction filtering before Top 15, ordering and empty-side checks passed.');
