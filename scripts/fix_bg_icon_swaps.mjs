import fs from 'node:fs/promises';
import path from 'node:path';

const REPORT_PATH = 'assets/bg-icons-report.json';

function norm(s = '') {
  return String(s)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ß/g, 'ss')
    .replace(/\.webp$/i, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

const STOP = new Set([
  'upgrade','production','unlock','call','in','squad','team','global','left','right',
  'the','and','or','route','package','ability','tank','vehicle','ger','uk','us',
  'german','british','american','afrika','korps','battlegroups','export','flatten',
]);

function tokens(s = '') {
  return norm(s).split(/\s+/).filter(t => t && !STOP.has(t) && !/^\d+[a-z]?$/.test(t));
}

function choiceFromKey(key = '') {
  return String(key).split('|').at(-1) || '';
}

function semanticRef(ref = '') {
  const tail = String(ref).split('/').at(-1) || '';
  // Most battlegroup refs are <bg>_(left|right)_<tier>_<ability>.
  // Strip the battlegroup/tree scaffolding so it cannot incorrectly match the
  // battlegroup name itself (the cause of the Breakthrough swap).
  const stripped = tail.replace(/^.*?_(?:left|right)_\d+[a-z]?_/, '');
  return stripped || tail;
}

function assetDescriptor(entry) {
  const upstream = path.basename(entry?.upstream || '').replace(/\.webp$/i, '');
  return `${upstream} ${semanticRef(entry?.ref || '')}`;
}

function semanticScore(choice, entry) {
  const a = tokens(choice);
  const b = tokens(assetDescriptor(entry));
  if (!a.length || !b.length) return 0;
  let score = 0;
  for (const t of a) {
    if (b.includes(t)) score += 6;
    else if (b.some(x => x.startsWith(t) || t.startsWith(x))) score += 2;
  }
  const ca = a.join('');
  const cb = b.join('');
  if (ca && cb && (cb.includes(ca) || ca.includes(cb))) score += 10;
  return score;
}

async function swapGeneratedAssets(a, b) {
  const [bufA, bufB] = await Promise.all([fs.readFile(a.path), fs.readFile(b.path)]);
  await Promise.all([fs.writeFile(a.path, bufB), fs.writeFile(b.path, bufA)]);
  [a.upstream, b.upstream] = [b.upstream, a.upstream];
  [a.ref, b.ref] = [b.ref, a.ref];
}

const report = JSON.parse(await fs.readFile(REPORT_PATH, 'utf8'));
const resolved = report.resolved || [];
const byKey = new Map(resolved.map(x => [x.key, x]));
const corrected = [];

// Confirmed visual mismatch reported against the live site.
const knownPairs = [
  {
    a: 'Wehrmacht|Breakthrough|Assault Forces|1|Breakthrough',
    b: 'Wehrmacht|Breakthrough|Assault Forces|2|Mechanized Assault Group',
    wrongA: 'mechanized_assault_group',
    wrongB: 'breakthrough',
  },
];

for (const fix of knownPairs) {
  const a = byKey.get(fix.a);
  const b = byKey.get(fix.b);
  if (!a || !b) throw new Error(`Known icon-fix nodes missing: ${fix.a} / ${fix.b}`);

  const upA = norm(path.basename(a.upstream || ''));
  const upB = norm(path.basename(b.upstream || ''));
  const isKnownWrong = upA.includes(norm(fix.wrongA)) && upB.includes(norm(fix.wrongB));

  if (isKnownWrong) {
    await swapGeneratedAssets(a, b);
    corrected.push({ a: fix.a, b: fix.b, reason: 'confirmed cross-swap' });
  }
}

// Pairwise semantic QA across every branch. This does not auto-swap unknown
// cases; it records strong candidates for manual review so a fuzzy match cannot
// silently create another visual mix-up.
const groups = new Map();
for (const entry of resolved) {
  const parts = String(entry.key).split('|');
  if (parts.length < 5) continue;
  const groupKey = parts.slice(0, 3).join('|');
  if (!groups.has(groupKey)) groups.set(groupKey, []);
  groups.get(groupKey).push(entry);
}

const suspectedCrossSwaps = [];
for (const [group, entries] of groups) {
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      const a = entries[i];
      const b = entries[j];
      const ca = choiceFromKey(a.key);
      const cb = choiceFromKey(b.key);
      const currentA = semanticScore(ca, a);
      const currentB = semanticScore(cb, b);
      const swappedA = semanticScore(ca, b);
      const swappedB = semanticScore(cb, a);
      const current = currentA + currentB;
      const swapped = swappedA + swappedB;

      // Only flag strong mutual improvements. This deliberately favors
      // precision over recall because many CoH3 icons have abstract filenames.
      if (swapped >= current + 12 && swappedA > currentA && swappedB > currentB) {
        suspectedCrossSwaps.push({
          group,
          a: a.key,
          b: b.key,
          currentScore: current,
          swappedScore: swapped,
        });
      }
    }
  }
}

report.qa = {
  checkedAt: new Date().toISOString(),
  correctedKnownSwaps: corrected,
  suspectedCrossSwaps,
  note: 'Known confirmed swaps are corrected automatically. Other strong pairwise semantic candidates are reported only and are not auto-swapped.',
};

await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');
console.log(`Icon QA: corrected ${corrected.length} confirmed swap(s); ${suspectedCrossSwaps.length} additional strong candidate(s).`);
for (const x of suspectedCrossSwaps) console.log(` - REVIEW ${x.a} <-> ${x.b} (${x.currentScore} -> ${x.swappedScore})`);
