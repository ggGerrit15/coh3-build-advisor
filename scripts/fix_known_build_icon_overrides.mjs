import fs from 'node:fs/promises';
import path from 'node:path';

const HTML_PATH = 'index.html';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const OUT_DIR = 'assets/build-icons';
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const VERSION = 'v1.1.27';

const OVERRIDES = {
  'Wehrmacht|fallschirmpioneer paradrop': 'export/icons/races/german/infantry/fallschirmpioneers_ger.webp',
  'Wehrmacht|fallschirmpioneer squad paradrop': 'export/icons/races/german/infantry/fallschirmpioneers_ger.webp',
  'Wehrmacht|medical bunker station': 'export/icons/races/german/buildings/bunker_medical_ger.webp',
  'Wehrmacht|sturmpanzer iv brummbaer': 'export/icons/races/german/vehicles/brummbar_german.webp',

  // DAK: exact CoH3Stats artwork for the build-order labels used by the advisor.
  // These overrides run after the automatic matcher so generic/incorrect fallbacks
  // cannot replace the verified same-faction assets below.
  'DAK|kradschutzen': 'export/icons/races/afrika_corps/vehicles/kradschutzen_motorcycle_ak.webp',
  'DAK|250 half track': 'export/icons/races/afrika_corps/vehicles/halftrack_250_ak.webp',
  'DAK|light support kompanie': 'export/icons/races/afrika_corps/buildings/infanterie_support_ak.webp',
  'DAK|fire support elements': 'export/icons/races/afrika_corps/vehicles/halftrack_7_flak_ak.webp',
  'DAK|panzerjager': 'export/icons/races/afrika_corps/infantry/panzerjaegar_ak.webp',
  'DAK|flakvierling': 'export/icons/races/afrika_corps/vehicles/halftrack_7_flak_ak.webp',
  'DAK|flakvierling pak 38': 'export/icons/races/afrika_corps/vehicles/halftrack_7_flak_ak.webp',
  'DAK|panzerarmee kommand': 'export/icons/races/afrika_corps/buildings/panzer_kompanie_ak.webp',
  'DAK|support armor elements': 'export/icons/races/afrika_corps/vehicles/stug_iii_d_ak.webp',
  'DAK|254 recon tractor': 'export/icons/races/afrika_corps/vehicles/armored_tractor_254_ak.webp',
  'DAK|carro armato': 'export/icons/races/afrika_corps/vehicles/m13_40_ak.webp',
  'DAK|armored reserves before tiger call in': 'export/icons/races/afrika_corps/vehicles/tiger_ak.webp',
  'DAK|elefant only in a true heavy armor endgame': 'export/icons/races/afrika_corps/vehicles/elefant_tank_destroyer_ak.webp',

  // Two cards already had artwork in some profiles, but the automatic matcher
  // could select a merely similar asset. Pin them to the actual CoH3 icons too.
  'DAK|bersaglieri bolster': 'export/icons/races/afrika_corps/abilities/bersaglieri_bolster.webp',
  'DAK|convert 250 to 250 3 funkpanzerwagen': 'export/icons/races/afrika_corps/vehicles/vampire_ht_ak_icon.webp',

  // USF: use the full unit portrait rather than the small crossed-rifles symbol.
  // A distinct output filename below also busts the browser cache from v1.1.26.
  'USF|rifleman': 'export/icons/common/units/icons/13_rifleman.webp'
};

// Several builds use shorthand/plural wording for the same unit. French Rifle
// Section reuses the already-vendored, verified French infantry portrait.
const ALIASES = {
  'USF|french rifle section': 'USF|french',
  'USF|rifle': 'USF|rifleman',
  'USF|rifle 2': 'USF|rifleman',
  'USF|rifle 3': 'USF|rifleman',
  'USF|2 rifle core': 'USF|rifleman',
  'USF|3 rifles': 'USF|rifleman',
  'USF|optional third rifle': 'USF|rifleman',
  'USF|french 3': 'USF|french rifle section',
  'USF|more french rifle sections usually 3 4 total': 'USF|french rifle section',
  'USF|french rifle sections call ins': 'USF|french rifle section',
  'USF|third fourth french rifle section': 'USF|french rifle section',
  'USF|optional third french section on a wide infantry lane': 'USF|french rifle section'
};

const OUTPUT_NAMES = {
  'USF|rifleman': 'usf--rifleman-portrait.webp'
};

function slug(value = '') {
  return String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function isWebp(buf) {
  return buf.length >= 12 &&
    buf.subarray(0, 4).toString('ascii') === 'RIFF' &&
    buf.subarray(8, 12).toString('ascii') === 'WEBP';
}

async function download(rel) {
  for (const url of [`${CDN_RAW}/${rel}`, `${CDN}/${rel}`]) {
    const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-known-icon-fixes' } });
    if (!r.ok) continue;
    const buf = Buffer.from(await r.arrayBuffer());
    if (isWebp(buf)) return { buf, url };
  }
  throw new Error(`Could not download a valid WebP for ${rel}`);
}

await fs.mkdir(OUT_DIR, { recursive: true });
const manifest = JSON.parse(await fs.readFile(MANIFEST_PATH, 'utf8'));
const report = JSON.parse(await fs.readFile(REPORT_PATH, 'utf8'));
const applied = [];

for (const [key, rel] of Object.entries(OVERRIDES)) {
  const [faction, lookup] = key.split('|');
  const hit = await download(rel);
  const filename = OUTPUT_NAMES[key] || `${slug(faction)}--${slug(lookup)}.webp`;
  const outPath = path.join(OUT_DIR, filename).replaceAll('\\', '/');
  await fs.writeFile(outPath, hit.buf);
  manifest[key] = outPath;
  applied.push({ key, source: rel, localPath: outPath });
}

for (const [key, targetKey] of Object.entries(ALIASES)) {
  const localPath = manifest[targetKey];
  if (!localPath) throw new Error(`Missing alias target ${targetKey} for ${key}`);
  manifest[key] = localPath;
  applied.push({ key, source: `alias:${targetKey}`, localPath });
}

await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n');
report.knownIconOverrides = { version: VERSION, generatedAt: new Date().toISOString(), applied };
await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');

let html = await fs.readFile(HTML_PATH, 'utf8');
const block = `const BUILD_ORDER_ICON_PATHS=${JSON.stringify(manifest)};\n`;
if (!/const BUILD_ORDER_ICON_PATHS=.*?;\n/.test(html)) throw new Error('BUILD_ORDER_ICON_PATHS not found in index.html');
html = html.replace(/const BUILD_ORDER_ICON_PATHS=.*?;\n/, block);
html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
await fs.writeFile(HTML_PATH, html);
console.log(`Applied ${applied.length} known build-icon corrections; ${VERSION}.`);
