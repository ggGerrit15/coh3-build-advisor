import fs from 'node:fs/promises';
import path from 'node:path';

const DATA_TAG = 'v2.5.3-3';
const DATA_ROOT = `https://raw.githubusercontent.com/cohstats/coh3-data/${DATA_TAG}/data`;
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const CDN_TREE = 'https://api.github.com/repos/cohstats/coh3-cdn/git/trees/master?recursive=1';
const DATA_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const OUT_DIR = 'assets/build-icons';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const VERSION = 'v1.1.17';

const RACES = { Wehrmacht: 'german', DAK: 'afrika_korps', USF: 'american', British: 'british' };
const STRUCTURAL_KEYS = new Set(['extensions','squadexts','entityexts','race_list','race_data','info','ui_info','upgrade_bag','template_reference','locstring','requirements','actions','action_list','unit_list','loadout_data','type','value','data','children']);
const GENERIC = new Set(['squad','team','section','medium','heavy','light','unit','gun','tank','vehicle','the','production','unlock','upgrade','upgrades','call','in','anti','support']);
const BAD_MODIFIERS = ['command','king','flak','medical','mortar','bunker','emplacement','recon','flame','artillery','repair','fuel','scout'];

const EXACT_ICON_OVERRIDES = {
  'Wehrmacht|mg42': 'export/icons/races/german/team_weapons/hmg_mg42_ger.webp',
  'Wehrmacht|mortar': 'export/icons/races/german/team_weapons/mortar_81mm_ger.webp',
  'Wehrmacht|pak 40': 'export/icons/races/german/team_weapons/at_gun_75mm_ger.webp',
  'Wehrmacht|pak': 'export/icons/races/german/team_weapons/at_gun_75mm_ger.webp',
  'Wehrmacht|panzer iv': 'export/icons/races/german/vehicles/panzer_iv_german.webp',
  'Wehrmacht|panzer iv command tank': 'export/icons/races/german/vehicles/panzer_iv_cmd_german.webp',
  'Wehrmacht|tiger': 'export/icons/races/german/vehicles/tiger_german.webp',
  'Wehrmacht|251 half track': 'export/icons/races/german/vehicles/halftrack_german.webp',
  'Wehrmacht|stummel': 'export/icons/races/german/vehicles/halftrack_stummel_german.webp',
  'Wehrmacht|stummel conversion': 'export/icons/races/german/vehicles/halftrack_stummel_german.webp',
  'Wehrmacht|kettenkrad': 'export/icons/races/german/vehicles/kettenkrad_german.webp',
  'Wehrmacht|brummbar': 'export/icons/races/german/vehicles/brummbar_german.webp',
  'Wehrmacht|sturmtiger': 'export/icons/races/german/vehicles/sturmtiger_german.webp',
  'Wehrmacht|panther': 'export/icons/races/german/vehicles/panther_german.webp',
  'Wehrmacht|wirbelwind': 'export/icons/races/german/vehicles/wirbelwind_german.webp',
  'Wehrmacht|stug iii': 'export/icons/races/german/vehicles/stug_iii_german.webp',
  'Wehrmacht|stug iii g': 'export/icons/races/german/vehicles/stug_iii_german.webp',
  'Wehrmacht|obice': 'export/icons/races/german/team_weapons/tw_howitzer_obice_210_ger.webp'
};

function norm(value = '') {
  return String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}
function slug(value = '') { return norm(value).replaceAll(' ', '-').replace(/^-+|-+$/g, '') || 'icon'; }
function tokens(value = '') { return norm(value).split(' ').filter(Boolean); }
function stripOrdinal(value = '') { return String(value).replace(/^(?:2nd|second|3rd|third|4th|fourth|5th|fifth)\s+/i, '').trim(); }
function displayCore(raw = '') {
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
  return s.slice(0, cut).trim().replace(/\s*->.*$/i, '').trim();
}
function searchCore(raw = '') {
  let s = displayCore(raw);
  if (s.includes(' / ')) s = s.split(' / ')[0].trim();
  s = s.replace(/\s+from\s+.+$/i, '');
  s = s.replace(/\s+on\s+(?:fuel|munitions|point|resource).*/i, '');
  s = s.replace(/\s+(?:first|early|late|priority|only|as needed|when affordable)$/i, '');
  s = s.replace(/\s*\([^)]*\)\s*$/g, '');
  return s.trim();
}
function visualLookup(raw = '') { return norm(displayCore(raw)); }
function searchLookup(raw = '') { return norm(searchCore(raw)); }
function simplified(value = '') { return tokens(value).filter(t => !GENERIC.has(t)).join(' '); }
function expectedCategory(step = '') {
  const q = norm(step);
  if (/(kompanie|company|quarters|bunker|station|camp|command post|support center|motor pool|tank depot|armory|hq|elements|training center|headquarters)/.test(q)) return 'buildings';
  if (/(mg\d*|hmg|pak\b|mortar|howitzer|pounder|at gun|anti tank gun|flak 36|flak 38|recoilless)/.test(q)) return 'team_weapons';
  if (/(upgrade|package|training|conversion|refit|bars?\b|grenade package|officer quarters)/.test(q)) return 'upgrades';
  if (/(half ?track|kettenkrad|\b\d+ rad\b|greyhound|chaffee|sherman|hellcat|stuart|dingo|humber|grant|centaur|churchill|panzer|tiger|stug|stummel|marder|wirbelwind|brummbar|tractor|truck|carro|semovente|flakvierling|weasel|bishop)/.test(q)) return 'vehicles';
  return 'infantry';
}

async function getJson(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-build-icon-sync', accept: 'application/vnd.github+json' } });
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
function rawIconValues(obj) {
  const out = [];
  for (const k of ['ui_squad_symbol_icon_name_override','symbol_icon_name','ui_squad_icon_override','icon_name','ui_squad_portrait_icon_override','portrait_name']) {
    const v = obj?.[k];
    if (typeof v === 'string' && v.trim()) out.push(v.trim());
  }
  return [...new Set(out)];
}
function iconMatchesRace(icon, race) {
  const p = String(icon).toLowerCase();
  if (p.includes(`/races/${race}/`)) return true;
  if (p.startsWith(`races/${race}/`)) return true;
  return p.includes('/common/') || p.startsWith('common/');
}
function iconValues(obj, race) {
  const vals = rawIconValues(obj);
  const own = vals.filter(x => iconMatchesRace(x, race) && (String(x).includes(`/races/${race}/`) || String(x).startsWith(`races/${race}/`)));
  const common = vals.filter(x => iconMatchesRace(x, race) && !own.includes(x));
  return [...own, ...common];
}
function collectUiCandidates(node, loc, out, race, pathParts = [], depth = 0) {
  if (!node || depth > 13) return;
  if (Array.isArray(node)) {
    for (const item of node) collectUiCandidates(item, loc, out, race, pathParts, depth + 1);
    return;
  }
  if (typeof node !== 'object') return;

  const icons = iconValues(node, race);
  if (icons.length) {
    const ids = [locId(node.screen_name), locId(node.screen_name_short), locId(node.ui_name), locId(node.display_name)].filter(Boolean);
    const names = ids.map(id => loc[id]).filter(Boolean);
    const usefulPath = pathParts.filter(x => x && !STRUCTURAL_KEYS.has(x)).slice(-7).join(' ');
    for (const name of names) out.push({ name, normName: norm(name), alias: norm(usefulPath), icons });
    if (!names.length && usefulPath) out.push({ name: usefulPath, normName: norm(usefulPath), alias: norm(usefulPath), icons });
  }

  for (const [k, v] of Object.entries(node)) {
    if (v && typeof v === 'object') collectUiCandidates(v, loc, out, race, [...pathParts, k], depth + 1);
  }
}
function candidateScore(step, c) {
  const q = norm(step), qs = simplified(q), ns = simplified(c.normName), as = simplified(c.alias);
  if (!q) return -999;
  let score = 0;
  if (c.normName === q) score += 1000;
  if (ns && ns === qs) score += 700;
  if (c.normName.includes(q) || q.includes(c.normName)) score += 170;
  if (qs && (ns.includes(qs) || qs.includes(ns))) score += 130;
  if (c.alias && (c.alias.includes(q) || q.includes(c.alias))) score += 80;
  if (qs && as && (as.includes(qs) || qs.includes(as))) score += 65;

  const qt = tokens(q).filter(x => !GENERIC.has(x));
  const nt = new Set([...tokens(c.normName), ...tokens(c.alias)]);
  for (const t of qt) {
    if (nt.has(t)) score += /^\d+$/.test(t) ? 55 : 32;
    else if ([...nt].some(h => h.length >= 4 && t.length >= 4 && (h.startsWith(t) || t.startsWith(h)))) score += 8;
    else score -= /^\d+$/.test(t) ? 120 : 18;
  }
  for (const roman of ['ii','iii','iv','v','vi']) if (qt.includes(roman) && !nt.has(roman)) score -= 100;
  for (const mod of BAD_MODIFIERS) if (!q.includes(mod) && (c.normName.includes(mod) || c.alias.includes(mod))) score -= 150;
  if (q.includes('pioneer') && !nt.has('pioneer') && !nt.has('pioneers')) score -= 120;
  if (q.includes('grenadier') && !nt.has('grenadier') && !nt.has('grenadiers')) score -= 120;
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
async function fetchIconRel(rel) {
  const clean = String(rel).replace(/^public\//, '');
  for (const url of [`${CDN_RAW}/${clean}`, `${CDN}/${clean}`]) {
    const buf = await getBinary(url);
    if (buf) return { buf, rel: clean, url };
  }
  return null;
}
async function fetchIcon(iconNames) {
  for (const icon of iconNames) {
    for (const rel of normalizeIconPath(icon)) {
      const hit = await fetchIconRel(rel);
      if (hit) return hit;
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
      const display = displayCore(raw), search = searchCore(raw), lookup = visualLookup(raw), searchKey = searchLookup(raw);
      if (display && lookup.length >= 2 && searchKey.length >= 2) out.push({ faction, raw: String(raw), display, search, lookup, searchKey });
    }
  }
  if (Array.isArray(node.variants)) for (const v of node.variants) collectBuildSteps(v, out, faction, seen);
  for (const [k, v] of Object.entries(node)) {
    if (k === 'build' || k === 'variants') continue;
    if (v && typeof v === 'object') collectBuildSteps(v, out, faction, seen);
  }
}
function assetBase(pathName) {
  const file = pathName.split('/').pop().replace(/\.webp$/i, '').replace(/_portrait$/i, '');
  return norm(file.replace(/_(?:german|ger|british|uk|american|us|afrika_korps|afrika|ak|dak)$/i, ''));
}
function categoryFromPath(pathName) {
  const m = /\/icons\/races\/[^/]+\/([^/]+)\//.exec(pathName);
  return m ? m[1] : '';
}
function buildAssetIndex(tree, race) {
  const prefix = `public/export/icons/races/${race}/`;
  return (tree?.tree || []).filter(x => x.type === 'blob' && x.path.startsWith(prefix) && x.path.endsWith('.webp') && !x.path.endsWith('_portrait.webp')).map(x => ({ path: x.path, rel: x.path.replace(/^public\//, ''), base: assetBase(x.path), category: categoryFromPath(x.path) }));
}
function assetScore(step, asset) {
  const q = norm(step), qs = simplified(q), a = asset.base, as = simplified(a);
  if (!q || !a) return -999;
  let score = 0;
  if (a === q) score += 900;
  if (as && as === qs) score += 650;
  if (a.includes(q) || q.includes(a)) score += 150;
  const qt = tokens(q).filter(x => !GENERIC.has(x));
  const at = new Set(tokens(a));
  for (const t of qt) {
    if (at.has(t)) score += /^\d+$/.test(t) ? 60 : 34;
    else if ([...at].some(h => h.length >= 4 && t.length >= 4 && (h.startsWith(t) || t.startsWith(h)))) score += 8;
    else score -= /^\d+$/.test(t) ? 140 : 20;
  }
  for (const mod of BAD_MODIFIERS) if (!q.includes(mod) && a.includes(mod)) score -= 180;
  const expected = expectedCategory(q);
  if (asset.category === expected) score += 90;
  else if (expected === 'infantry' && asset.category === 'symbols') score += 20;
  else if (['infantry','vehicles','team_weapons','buildings','upgrades'].includes(asset.category)) score -= 30;
  return score;
}
function overrideFor(faction, step) {
  const q = norm(step);
  const exact = EXACT_ICON_OVERRIDES[`${faction}|${q}`];
  if (exact) return exact;
  const keys = Object.entries(EXACT_ICON_OVERRIDES).filter(([k]) => k.startsWith(`${faction}|`)).map(([k, v]) => [k.split('|').slice(1).join('|'), v]).sort((a,b) => b[0].length - a[0].length);
  for (const [key, rel] of keys) if (q === key || q.startsWith(`${key} `)) return rel;
  return null;
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

await fs.rm(OUT_DIR, { recursive: true, force: true });
await fs.mkdir(OUT_DIR, { recursive: true });
const data = JSON.parse(await fs.readFile(DATA_PATH, 'utf8'));
const [loc, cdnTree] = await Promise.all([getJson(`${DATA_ROOT}/locstring.json`), getJson(CDN_TREE)]);
const steps = [];
collectBuildSteps(data, steps);
const uniqueSteps = [...new Map(steps.map(s => [`${s.faction}|${s.lookup}`, s])).values()];

const manifest = {};
const report = { dataTag: DATA_TAG, generatedAt: new Date().toISOString(), total: uniqueSteps.length, resolved: [], unresolved: [], rejectedLowConfidence: [] };

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
  collectUiCandidates(sbps, loc, candidates, race, [race, 'sbps']);
  collectUiCandidates(ebps, loc, candidates, race, [race, 'ebps']);
  collectUiCandidates(upgrades, loc, candidates, race, [race, 'upgrade']);
  const assets = buildAssetIndex(cdnTree, race);

  for (const step of needed) {
    let chosen = null;
    const manualRel = overrideFor(faction, step.searchKey);
    if (manualRel) {
      const icon = await fetchIconRel(manualRel);
      if (icon) chosen = { icon, method: 'manual-override', matched: manualRel, score: 2000 };
    }

    if (!chosen) {
      const ranked = candidates.map(c => ({ c, score: candidateScore(step.search, c) })).sort((a, b) => b.score - a.score);
      const best = ranked[0], second = ranked[1];
      const margin = best ? best.score - (second?.score ?? -999) : 0;
      const acceptable = best && (best.score >= 260 || (best.score >= 170 && margin >= 60) || best.c.normName === norm(step.search));
      if (acceptable) {
        const icon = await fetchIcon(best.c.icons);
        if (icon) chosen = { icon, method: 'coh3-data', matched: best.c.name, score: best.score, margin, candidateIcons: best.c.icons };
      } else if (best) {
        report.rejectedLowConfidence.push({ faction, step: step.display, search: step.search, candidate: best.c.name, score: best.score, margin });
      }
    }

    if (!chosen) {
      const rankedAssets = assets.map(a => ({ a, score: assetScore(step.search, a) })).sort((x, y) => y.score - x.score);
      const best = rankedAssets[0], second = rankedAssets[1], margin = best ? best.score - (second?.score ?? -999) : 0;
      if (best && (best.score >= 200 || (best.score >= 145 && margin >= 45))) {
        const icon = await fetchIconRel(best.a.rel);
        if (icon) chosen = { icon, method: 'cdn-filename', matched: best.a.path, score: best.score, margin };
      }
    }

    if (!chosen) {
      report.unresolved.push({ faction, step: step.display, search: step.search, lookup: step.lookup, reason: 'no high-confidence same-faction CoH3Stats icon match' });
      continue;
    }

    const fileName = `${slug(faction)}--${slug(step.lookup)}.webp`;
    const outPath = path.join(OUT_DIR, fileName);
    await fs.writeFile(outPath, chosen.icon.buf);
    const localPath = outPath.replaceAll('\\', '/');
    manifest[`${faction}|${step.lookup}`] = localPath;
    report.resolved.push({ faction, step: step.display, search: step.search, lookup: step.lookup, matched: chosen.matched, method: chosen.method, score: chosen.score, margin: chosen.margin ?? null, sourceIcon: chosen.icon.rel, localPath });
  }
}

report.resolvedCount = report.resolved.length;
report.unresolvedCount = report.unresolved.length;
report.coveragePct = Number((100 * report.resolvedCount / Math.max(1, report.total)).toFixed(1));
await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n');
await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');
let html = await fs.readFile(HTML_PATH, 'utf8');
html = patchHtml(html, manifest);
await fs.writeFile(HTML_PATH, html);
console.log(`Build icon sync complete: ${report.resolvedCount}/${report.total} (${report.coveragePct}%) locally vendored; ${report.unresolvedCount} unresolved.`);
