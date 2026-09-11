import fs from 'node:fs/promises';
import path from 'node:path';

const DATA_TAG = 'v2.5.3-3';
const DATA_ROOT = `https://raw.githubusercontent.com/cohstats/coh3-data/${DATA_TAG}/data`;
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const DATA_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const OUT_DIR = 'assets/build-icons';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const VERSION = 'v1.1.16';

const RACES = { Wehrmacht: 'german', DAK: 'afrika_korps', USF: 'american', British: 'british' };
const STRUCTURAL_KEYS = new Set(['extensions','squadexts','entityexts','race_list','race_data','info','ui_info','upgrade_bag','template_reference','locstring','requirements','actions','action_list','unit_list','loadout_data','type','value','data','children']);

function norm(value = '') {
  return String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}
function slug(value = '') { return norm(value).replaceAll(' ', '-').replace(/^-+|-+$/g, '') || 'icon'; }
function tokens(value = '') { return norm(value).split(' ').filter(Boolean); }
function stripOrdinal(value = '') { return String(value).replace(/^(?:2nd|second|3rd|third|4th|fourth|5th|fifth)\s+/i, '').trim(); }
function coreStep(raw = '') {
  let s = String(raw).trim();
  s = s.replace(/^(?:Start|Starting unit)\s*:\s*/i, '');
  s = stripOrdinal(s);
  s = s.replace(/^\[[^\]]+\]\s*/i, '');
  const colon = /^(?:If|When|Against|Vs\.?|Versus)\b[^:]*:\s*(.+)$/i.exec(s);
  if (colon) s = colon[1];
  const lower = s.toLowerCase();
  let cut = s.length;
  for (const marker of [' only vs ', ' if ', ' when ', ' after ', ' unless ', ' once ', ' depending ', ' according to ']) {
    const i = lower.indexOf(marker);
    if (i > 0) cut = Math.min(cut, i);
  }
  s = s.slice(0, cut).trim();
  if (s.includes(' / ')) s = s.split(' / ')[0].trim();
  s = s.replace(/\s*->.*$/i, '').trim();
  return s;
}
function visualLookup(raw = '') { return norm(stripOrdinal(coreStep(raw))); }

async function getJson(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-build-icon-sync' } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${url}`);
  return r.json();
}
async function getBinary(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-build-icon-sync' } });
  if (!r.ok) return null;
  const b = Buffer.from(await r.arrayBuffer());
  if (b.length < 250) return null;
  return b;
}
function locId(value) {
  if (value == null) return null;
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (typeof value === 'object') {
    if (value.locstring?.value != null) return String(value.locstring.value);
    if (value.value != null && (typeof value.value === 'string' || typeof value.value === 'number')) return String(value.value);
  }
  return null;
}
function iconValues(obj) {
  const out = [];
  for (const k of ['icon_name','symbol_icon_name','portrait_name','ui_squad_icon_override','ui_squad_symbol_icon_name_override','ui_squad_portrait_icon_override']) {
    const v = obj?.[k];
    if (typeof v === 'string' && v.trim()) out.push(v.trim());
  }
  return [...new Set(out)];
}
function collectUiCandidates(node, loc, out, pathParts = [], depth = 0) {
  if (!node || depth > 13) return;
  if (Array.isArray(node)) {
    for (const item of node) collectUiCandidates(item, loc, out, pathParts, depth + 1);
    return;
  }
  if (typeof node !== 'object') return;

  const icons = iconValues(node);
  if (icons.length) {
    const ids = [locId(node.screen_name), locId(node.screen_name_short), locId(node.ui_name), locId(node.display_name)].filter(Boolean);
    const names = ids.map(id => loc[id]).filter(Boolean);
    const usefulPath = pathParts.filter(x => x && !STRUCTURAL_KEYS.has(x)).slice(-7).join(' ');
    for (const name of names) out.push({ name, normName: norm(name), alias: norm(usefulPath), icons });
    if (!names.length && usefulPath) out.push({ name: usefulPath, normName: norm(usefulPath), alias: norm(usefulPath), icons });
  }

  for (const [k, v] of Object.entries(node)) {
    if (v && typeof v === 'object') collectUiCandidates(v, loc, out, [...pathParts, k], depth + 1);
  }
}
function candidateScore(step, c) {
  const q = norm(step);
  if (!q) return -1;
  if (c.normName === q) return 1000;
  let score = 0;
  if (c.normName.includes(q) || q.includes(c.normName)) score += 220;
  if (c.alias && (c.alias.includes(q) || q.includes(c.alias))) score += 150;
  const qt = tokens(q).filter(x => !['squad','team','medium','heavy','light','unit','gun','tank','vehicle','the'].includes(x));
  const hay = new Set([...tokens(c.normName), ...tokens(c.alias)]);
  for (const t of qt) {
    if (hay.has(t)) score += /^\d+$/.test(t) ? 18 : 30;
    else if ([...hay].some(h => h.length >= 4 && t.length >= 4 && (h.startsWith(t) || t.startsWith(h)))) score += 10;
  }
  if (qt.length && qt.every(t => hay.has(t))) score += 80;
  if (q.includes('pioneer') && !c.normName.includes('pioneer') && !c.alias.includes('pioneer')) score -= 80;
  if (q.includes('grenadier') && !c.normName.includes('grenadier') && !c.alias.includes('grenadier')) score -= 80;
  return score;
}
function normalizeIconPath(icon = '') {
  let p = String(icon).trim().replace(/^\/+/, '');
  if (!p) return [];
  p = p.replace(/\.png$/i, '').replace(/\.webp$/i, '');
  const bases = [];
  if (p.startsWith('export/')) bases.push(p);
  else if (p.startsWith('icons/')) bases.push(`export/${p}`);
  else bases.push(`export/icons/${p}`);
  return [...new Set(bases.flatMap(x => [`${x}.webp`, `${x}.png`]))];
}
async function fetchIcon(iconNames) {
  for (const icon of iconNames) {
    for (const rel of normalizeIconPath(icon)) {
      const urls = [`${CDN_RAW}/${rel}`, `${CDN}/${rel}`];
      for (const url of urls) {
        const buf = await getBinary(url);
        if (buf) return { buf, rel, url };
      }
    }
  }
  return null;
}
function collectBuildSteps(node, out, factionHint = null, seen = new Set()) {
  if (!node || typeof node !== 'object' || seen.has(node)) return;
  seen.add(node);
  if (Array.isArray(node)) {
    for (const item of node) collectBuildSteps(item, out, factionHint, seen);
    return;
  }
  const faction = node.faction || factionHint;
  if (faction && RACES[faction] && Array.isArray(node.build)) {
    for (const raw of node.build) {
      const core = coreStep(raw);
      const lookup = visualLookup(raw);
      if (core && lookup.length >= 2) out.push({ faction, raw: String(raw), core, lookup });
    }
  }
  if (Array.isArray(node.variants)) {
    for (const v of node.variants) collectBuildSteps(v, out, faction, seen);
  }
  for (const [k, v] of Object.entries(node)) {
    if (k === 'build' || k === 'variants') continue;
    if (v && typeof v === 'object') collectBuildSteps(v, out, faction, seen);
  }
}
function patchHtml(html, manifest) {
  const block = `const BUILD_ORDER_ICON_PATHS=${JSON.stringify(manifest)};\n`;
  if (/const BUILD_ORDER_ICON_PATHS=.*?;\n/.test(html)) html = html.replace(/const BUILD_ORDER_ICON_PATHS=.*?;\n/, block);
  else html = html.replace(/function buildStepIconUrls\(/, `${block}function buildStepIconUrls(`);

  const fn = `function buildStepIconUrls(p,stepName){const lookup=normalizeBuildIconToken(stepName),plain=lookup.replace(/^(?:2nd|second|3rd|third|4th|fourth|5th|fifth)\\s+/,''),f=p?.faction||'';const vendored=BUILD_ORDER_ICON_PATHS[\`${'${f}|${lookup}'}\`]||BUILD_ORDER_ICON_PATHS[\`${'${f}|${plain}'}\`];if(vendored)return[vendored];const local=Object.entries(typeof BATTLEGROUP_ICON_PATHS==='object'?BATTLEGROUP_ICON_PATHS:{}).find(([key])=>key.startsWith(f+'|'+(p?.battlegroup||'')+'|')&&lookup.includes(normalizeBuildIconToken(key.split('|').pop())));if(local)return[local[1]];const factionMap=BUILD_STEP_ICON_OVERRIDES[p?.faction]||{},keys=Object.keys(factionMap).sort((a,b)=>b.length-a.length);for(const key of keys){if(lookup===key||lookup.includes(key))return factionMap[key].flatMap(buildIconUrls)}return[]}`;
  html = html.replace(/function buildStepIconUrls\(p,stepName\)\{[\s\S]*?\}\nfunction loadBuildImageCandidates/, `${fn}\nfunction loadBuildImageCandidates`);
  html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
  return html;
}

await fs.mkdir(OUT_DIR, { recursive: true });
const data = JSON.parse(await fs.readFile(DATA_PATH, 'utf8'));
const loc = await getJson(`${DATA_ROOT}/locstring.json`);
const steps = [];
collectBuildSteps(data, steps);
const uniqueSteps = [...new Map(steps.map(s => [`${s.faction}|${s.lookup}`, s])).values()];

const manifest = {};
const report = { dataTag: DATA_TAG, generatedAt: new Date().toISOString(), total: uniqueSteps.length, resolved: [], unresolved: [] };

for (const [faction, race] of Object.entries(RACES)) {
  const needed = uniqueSteps.filter(s => s.faction === faction);
  if (!needed.length) continue;
  console.log(`Indexing ${faction} (${needed.length} unique build labels)...`);
  const [sbps, ebps, upgrades] = await Promise.all([
    getJson(`${DATA_ROOT}/chunked/sbps/races/${race}.json`),
    getJson(`${DATA_ROOT}/chunked/ebps/races/${race}.json`),
    getJson(`${DATA_ROOT}/chunked/upgrade/${race}.json`),
  ]);
  const candidates = [];
  collectUiCandidates(sbps, loc, candidates, [race, 'sbps']);
  collectUiCandidates(ebps, loc, candidates, [race, 'ebps']);
  collectUiCandidates(upgrades, loc, candidates, [race, 'upgrade']);

  for (const step of needed) {
    const ranked = candidates.map(c => ({ c, score: candidateScore(step.core, c) })).sort((a, b) => b.score - a.score);
    const best = ranked[0];
    if (!best || best.score < 45) {
      report.unresolved.push({ faction, step: step.core, lookup: step.lookup, reason: 'no confident CoH3Stats data match', best: best ? { name: best.c.name, score: best.score } : null });
      continue;
    }
    const icon = await fetchIcon(best.c.icons);
    if (!icon) {
      report.unresolved.push({ faction, step: step.core, lookup: step.lookup, reason: 'matched data record but icon file was not downloadable', best: { name: best.c.name, score: best.score, icons: best.c.icons } });
      continue;
    }
    const fileName = `${slug(faction)}--${slug(step.lookup)}.webp`;
    const outPath = path.join(OUT_DIR, fileName);
    await fs.writeFile(outPath, icon.buf);
    const localPath = outPath.replaceAll('\\', '/');
    manifest[`${faction}|${step.lookup}`] = localPath;
    report.resolved.push({ faction, step: step.core, lookup: step.lookup, matched: best.c.name, score: best.score, sourceIcon: icon.rel, localPath });
  }
}

report.resolvedCount = report.resolved.length;
report.unresolvedCount = report.unresolved.length;
await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n');
await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');
let html = await fs.readFile(HTML_PATH, 'utf8');
html = patchHtml(html, manifest);
await fs.writeFile(HTML_PATH, html);
console.log(`Build icon sync complete: ${report.resolvedCount}/${report.total} build labels vendored locally; ${report.unresolvedCount} unresolved.`);
