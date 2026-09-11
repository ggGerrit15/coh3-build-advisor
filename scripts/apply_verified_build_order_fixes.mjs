import fs from 'node:fs/promises';
import path from 'node:path';

const DATA_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const MANIFEST_PATH = 'assets/build-icons.json';
const REPORT_PATH = 'assets/build-icons-report.json';
const OUT_DIR = 'assets/build-icons';
const CDN_RAW = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const CDN = 'https://cdn.coh3stats.com';
const VERSION = 'v1.1.24';

const ICON_OVERRIDES = {
  'Wehrmacht|jager squad': 'export/icons/races/german/infantry/jaeger_ger.webp',
  'Wehrmacht|panzergrenadier': 'export/icons/races/german/infantry/panzer_grenadier_ger.webp',
  'Wehrmacht|panzergrenadier officer upgrade': 'export/icons/races/german/upgrades/officer_quarters_for_wehrmacht.webp',
  'Wehrmacht|officer upgrade when affordable': 'export/icons/races/german/upgrades/officer_quarters_for_wehrmacht.webp',
  'Wehrmacht|support elements if choosing stug iii g': 'export/icons/races/german/buildings/support_armory_ger.webp',
  'Wehrmacht|3 5t truck on fuel': 'export/icons/races/german/vehicles/2_5_truck_german.webp',
  'Wehrmacht|medical bunker': 'export/icons/races/german/buildings/bunker_medical_ger.webp'
};

function norm(value = '') {
  return String(value)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ß/g, 'ss')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function slug(value = '') {
  return norm(value).replaceAll(' ', '-') || 'icon';
}

function getProfile(data, battlegroup) {
  const profile = (data.profiles || []).find(
    p => p.faction === 'Wehrmacht' && p.battlegroup === battlegroup && p.mode === '1v1'
  );
  if (!profile) throw new Error(`Missing Wehrmacht ${battlegroup} 1v1 profile`);
  return profile;
}

function replaceBuildAt(profile, index, expectedOld, newValue) {
  const current = profile.build?.[index];
  if (current === newValue) return;
  if (!expectedOld.includes(current)) {
    throw new Error(
      `${profile.battlegroup} position ${index}: expected ${expectedOld.join(' / ')}, found ${current}`
    );
  }
  profile.build[index] = newValue;
}

async function syncEmbeddedProfiles(data) {
  let html = await fs.readFile(HTML_PATH, 'utf8');
  const profilesBlock = `const PROFILES=${JSON.stringify(data.profiles || [])};\n`;
  const profilesPattern = /const PROFILES=.*?;\nconst MATCHUPS=/;

  if (!profilesPattern.test(html)) {
    throw new Error('Embedded PROFILES block not found in index.html');
  }

  html = html.replace(profilesPattern, `${profilesBlock}const MATCHUPS=`);
  html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
  await fs.writeFile(HTML_PATH, html);
}

async function applyDataFixes() {
  const data = JSON.parse(await fs.readFile(DATA_PATH, 'utf8'));

  // UI numbering treats build[0] as START, so user-visible position N maps to build[N].
  replaceBuildAt(getProfile(data, 'Mechanized'), 10, ['Medical Station'], 'Medical Bunker');
  replaceBuildAt(getProfile(data, 'Terror'), 5, ['Medical Station'], 'Medical Bunker');
  replaceBuildAt(getProfile(data, 'Italian Coastal'), 6, ['Medical Station'], 'Medical Bunker');

  const siege = getProfile(data, 'Siege Breaker');
  siege.build = (siege.build || []).filter(step => step !== 'Siege Camp');
  siege.verdict = 'A strong pressure build when the opponent leans on MGs, AT guns or fixed positions. This default route uses Grinding Advance; Construct Siege Camp is the mutually exclusive alternative.';

  siege.target = (siege.target || []).filter(item => item !== 'Siege Camp');
  if (!siege.target.includes('Grinding Advance')) {
    siege.target.splice(Math.min(5, siege.target.length), 0, 'Grinding Advance');
  }

  siege.tips ||= [];
  if (siege.tips.length) {
    siege.tips[0] = 'The default battlegroup route uses Grinding Advance; Construct Siege Camp is mutually exclusive and is therefore not part of this build.';
  } else {
    siege.tips.push('The default battlegroup route uses Grinding Advance; Construct Siege Camp is mutually exclusive and is therefore not part of this build.');
  }

  if (siege.branches?.[0]) {
    siege.branches[0][1] = 'Use Grinding Advance to displace the support-weapon line, then push with Panzergrenadiers and armor';
  }
  if (siege.branches?.[1]) {
    siege.branches[1][1] = 'Play conventional T3→T4 and use Grinding Advance only when it creates a clean push';
  }

  if (siege.legacy?.build) {
    siege.legacy.build = siege.legacy.build.filter(step => step !== 'Siege Camp');
  }

  const siegeQa = 'Grinding Advance and Construct Siege Camp are mutually exclusive Siegeworks Tier 2 choices; this build uses Grinding Advance, so Siege Camp is not included.';
  siege.techQaNotes ||= [];
  if (!siege.techQaNotes.includes(siegeQa)) siege.techQaNotes.push(siegeQa);

  await fs.writeFile(DATA_PATH, JSON.stringify(data, null, 2) + '\n');
  await syncEmbeddedProfiles(data);
  console.log('Applied verified Wehrmacht build-order content corrections and synchronized embedded live profiles.');
}

async function download(rel) {
  for (const url of [`${CDN_RAW}/${rel}`, `${CDN}/${rel}`]) {
    const response = await fetch(url, {
      headers: { 'user-agent': 'coh3-build-advisor-verified-build-fixes' }
    });
    if (!response.ok) continue;
    const buf = Buffer.from(await response.arrayBuffer());
    if (buf.length >= 250) return { buf, url };
  }
  throw new Error(`Could not download verified CoH3 icon: ${rel}`);
}

async function applyIconFixes() {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const manifest = JSON.parse(await fs.readFile(MANIFEST_PATH, 'utf8'));
  const report = JSON.parse(await fs.readFile(REPORT_PATH, 'utf8'));
  const applied = [];

  for (const [key, rel] of Object.entries(ICON_OVERRIDES)) {
    const [faction, lookup] = key.split('|');
    const hit = await download(rel);
    const localPath = path
      .join(OUT_DIR, `${slug(faction)}--${slug(lookup)}.webp`)
      .replaceAll('\\', '/');
    await fs.writeFile(localPath, hit.buf);
    manifest[key] = localPath;
    applied.push({ key, source: rel, localPath });
  }

  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n');

  report.verifiedBuildOrderFixes = {
    version: VERSION,
    generatedAt: new Date().toISOString(),
    source: 'User-verified Wehrmacht build-order QA with exact CoH3Stats CDN assets',
    appliedIcons: applied
  };
  await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');

  let html = await fs.readFile(HTML_PATH, 'utf8');
  const manifestBlock = `const BUILD_ORDER_ICON_PATHS=${JSON.stringify(manifest)};\n`;
  if (!/const BUILD_ORDER_ICON_PATHS=.*?;\n/.test(html)) {
    throw new Error('BUILD_ORDER_ICON_PATHS not found in index.html');
  }
  html = html.replace(/const BUILD_ORDER_ICON_PATHS=.*?;\n/, manifestBlock);
  html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
  await fs.writeFile(HTML_PATH, html);

  console.log(`Applied ${applied.length} verified exact icon mappings; ${VERSION}.`);
}

const args = new Set(process.argv.slice(2));
if (args.size === 0) {
  await applyDataFixes();
  await applyIconFixes();
} else {
  if (args.has('--data')) await applyDataFixes();
  if (args.has('--icons')) await applyIconFixes();
}
