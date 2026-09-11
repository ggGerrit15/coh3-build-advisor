import fs from 'node:fs/promises';
import path from 'node:path';

const HTML_PATH = 'index.html';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const OUT_DIR = 'assets/build-icons';
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const VERSION = 'v1.1.19';

const OVERRIDES = {
  'Wehrmacht|fallschirmpioneer paradrop': 'export/icons/races/german/infantry/fallschirmpioneers_ger.webp',
  'Wehrmacht|fallschirmpioneer squad paradrop': 'export/icons/races/german/infantry/fallschirmpioneers_ger.webp',
  'Wehrmacht|medical bunker station': 'export/icons/races/german/buildings/bunker_medical_ger.webp',
  'Wehrmacht|sturmpanzer iv brummbaer': 'export/icons/races/german/vehicles/brummbar_german.webp'
};

function slug(value = '') {
  return String(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}
async function download(rel) {
  for (const url of [`${CDN_RAW}/${rel}`, `${CDN}/${rel}`]) {
    const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-known-icon-fixes' } });
    if (!r.ok) continue;
    const buf = Buffer.from(await r.arrayBuffer());
    if (buf.length >= 250) return { buf, url };
  }
  throw new Error(`Could not download ${rel}`);
}

await fs.mkdir(OUT_DIR, { recursive: true });
const manifest = JSON.parse(await fs.readFile(MANIFEST_PATH, 'utf8'));
const report = JSON.parse(await fs.readFile(REPORT_PATH, 'utf8'));
const applied = [];

for (const [key, rel] of Object.entries(OVERRIDES)) {
  const [faction, lookup] = key.split('|');
  const hit = await download(rel);
  const outPath = path.join(OUT_DIR, `${slug(faction)}--${slug(lookup)}.webp`).replaceAll('\\', '/');
  await fs.writeFile(outPath, hit.buf);
  manifest[key] = outPath;
  applied.push({ key, source: rel, localPath: outPath });
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
