import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const DATA_TAG = 'v2.5.3-3';
const DATA_ROOT = `https://raw.githubusercontent.com/cohstats/coh3-data/${DATA_TAG}/data`;
const CDN_RAW_ROOT = 'https://raw.githubusercontent.com/cohstats/coh3-cdn/master/public';
const JSON_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const ASSET_DIR = 'assets/icons';
const MANIFEST_PATH = 'assets/bg-icons.json';
const REPORT_PATH = 'assets/bg-icons-report.json';
const VERSION = 'v1.1.7';

const RACE_KEYS = { Wehrmacht: 'german', DAK: 'afrika_korps', USF: 'american', British: 'british' };
const BG_KEY_OVERRIDES = {
  'USF|Heavy Weapons': 'special_weapons',
  'British|Air and Sea': 'british_air_and_sea',
  'British|Heavy Armor': 'british_armored',
  'DAK|Battlefield Espionage': 'subterfuge',
};
const ICON_OVERRIDES = {
  'Wehrmacht|Luftwaffe|Air-to-Ground|0|Reconnaissance Run': 'export/icons/races/german/abilities/reconissance_run.webp',
  'Wehrmacht|Luftwaffe|Air-to-Ground|0|Stuka Strafing Run': 'export/icons/races/german/abilities/stuka_strafing_run.webp',
  'Wehrmacht|Luftwaffe|Air-to-Ground|1|Fallschirmjäger Squad Paradrop': 'export/icons/races/german/symbols/fallshirmjagers_ger.webp',
  'Wehrmacht|Luftwaffe|Air-to-Ground|2|Fragmentation Bombs': 'export/icons/races/german/abilities/fragmentation_bombs.webp',
  'Wehrmacht|Luftwaffe|Air-to-Ground|2|Stuka Loiter': 'export/icons/races/german/abilities/stuka_attack_loiter.webp',
  'Wehrmacht|Luftwaffe|Field Support|0|Fallschirmpioneer Squad Paradrop': 'export/icons/races/german/symbols/fallshirmpioneers_ger.webp',
  'Wehrmacht|Luftwaffe|Field Support|1|LG40 Recoilless Gun Paradrop': 'export/icons/races/german/symbols/lg_40_anti-tank_gun.webp',
  'Wehrmacht|Luftwaffe|Field Support|1|Flak 38 Anti-Air Emplacement': 'export/icons/races/german/team_weapons/tw_20mm_emplacement_ger.webp',
  'Wehrmacht|Luftwaffe|Field Support|2|Infantry Reserves': 'export/icons/races/german/abilities/infantry_reserves.webp',
  'Wehrmacht|Luftwaffe|Field Support|2|Flak 36 Anti-tank Emplacement': 'export/icons/races/german/team_weapons/tw_88mm_emplacement_ger.webp',
};

function norm(s = '') {
  return String(s).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, ' ').trim();
}
function tokens(s = '') {
  return new Set(norm(s).split(/\s+/).filter(Boolean).map(t => t.replace(/^15cwt$/, 'cwt')));
}
function scoreBg(label, key) {
  const a = tokens(label);
  const b = tokens(String(key).replace(/^(british|german|american|afrika_korps)_/, '').replaceAll('_', ' '));
  let score = 0;
  for (const t of a) {
    if (b.has(t)) score += 3;
    else if ([...b].some(x => x.includes(t) || t.includes(x))) score += 1;
  }
  return score;
}
function resolveRawBattlegroupKey(faction, bg, raceBgs) {
  const override = BG_KEY_OVERRIDES[`${faction}|${bg}`];
  if (override && raceBgs?.[override]) return override;
  return Object.keys(raceBgs || {}).sort((a, b) => scoreBg(bg, b) - scoreBg(bg, a))[0] || null;
}
function refTail(ref = '') { return String(ref).split('/').pop() || ''; }
function choiceRefScore(choice, ref) {
  const stop = new Set(['upgrade', 'production', 'unlock', 'call', 'in', 'squad', 'team', 'global', 'left', 'right', 'the', 'and', 'or', 'route', 'package', 'ability', 'tank', 'vehicle']);
  const a = [...tokens(choice)].filter(x => !stop.has(x));
  const b = [...tokens(refTail(ref).replaceAll('_', ' '))].filter(x => !stop.has(x) && !['ak', 'uk', 'us'].includes(x));
  let score = 0;
  for (const t of a) {
    if (b.includes(t)) score += 6;
    else if (b.some(x => x.startsWith(t) || t.startsWith(x))) score += 2;
  }
  const compactChoice = norm(choice).replaceAll(' ', '');
  const compactRef = norm(refTail(ref)).replaceAll(' ', '');
  if (compactChoice && (compactRef.includes(compactChoice) || compactChoice.includes(compactRef))) score += 12;
  return score;
}
function matchChoicesToRefs(choices, refs) {
  const remaining = new Set(refs);
  const out = {};
  const ranked = [];
  for (const choice of choices) for (const ref of refs) ranked.push({ choice, ref, score: choiceRefScore(choice, ref) });
  ranked.sort((a, b) => b.score - a.score);
  const usedChoices = new Set();
  for (const x of ranked) {
    if (x.score <= 0 || usedChoices.has(x.choice) || !remaining.has(x.ref)) continue;
    out[x.choice] = x.ref;
    usedChoices.add(x.choice);
    remaining.delete(x.ref);
  }
  const missing = choices.filter(x => !out[x]);
  const left = [...remaining];
  if (missing.length === left.length) missing.forEach((choice, i) => { out[choice] = left[i]; });
  return out;
}
function keyFor(faction, bg, branch, tierIndex, choice) { return `${faction}|${bg}|${branch}|${tierIndex}|${choice}`; }
function slug(s) { return norm(s).replaceAll(' ', '-').replace(/^-+|-+$/g, '') || 'icon'; }
function outputName(faction, bg, branch, tierIndex, choice) {
  return `${slug(faction)}--${slug(bg)}--${slug(branch)}--t${tierIndex + 1}--${slug(choice)}.webp`;
}
async function getJson(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-icon-sync' } });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${url}`);
  return r.json();
}
async function getBinary(url) {
  const r = await fetch(url, { headers: { 'user-agent': 'coh3-build-advisor-icon-sync' } });
  if (!r.ok) return null;
  const ct = r.headers.get('content-type') || '';
  if (!ct.includes('image') && !url.endsWith('.webp')) return null;
  return Buffer.from(await r.arrayBuffer());
}
function normalizeIconPath(icon = '') {
  let p = String(icon || '').trim().replace(/^\/+/, '');
  if (!p) return '';
  if (/\.png$/i.test(p)) p = p.replace(/\.png$/i, '.webp');
  else if (!/\.webp$/i.test(p)) p += '.webp';
  if (!p.startsWith('export/') && !p.startsWith('export_flatten/')) p = `export/${p}`;
  return p;
}
function extractIconNames(rec) {
  const preferred = [
    rec?.upgrade_bag?.ui_info?.icon_name,
    rec?.upgrade_bag?.ui_info?.symbol_icon_name,
    rec?.upgrade_bag?.ui_squad_icon_override,
    rec?.upgrade_bag?.ui_squad_portrait_icon_override,
    rec?.upgrade_bag?.ui_squad_symbol_icon_name_override,
    rec?.upgrade_bag?.ui_kicker_icon_name,
    rec?.ui_info?.icon_name,
  ];
  const all = [];
  const seen = new Set();
  function walk(x, depth = 0) {
    if (!x || depth > 8) return;
    if (Array.isArray(x)) return x.forEach(v => walk(v, depth + 1));
    if (typeof x !== 'object') return;
    for (const [k, v] of Object.entries(x)) {
      if (typeof v === 'string' && /icon/i.test(k) && (v.includes('icons/') || v.includes('races/'))) all.push(v);
      else if (typeof v === 'object') walk(v, depth + 1);
    }
  }
  walk(rec);
  return [...preferred, ...all].filter(Boolean).filter(x => {
    const k = String(x);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}
function indexRecords(data) {
  const map = new Map();
  if (data && typeof data === 'object') {
    for (const [k, v] of Object.entries(data)) if (v && typeof v === 'object') map.set(k, v);
  }
  function walk(x, keyHint = '', depth = 0) {
    if (!x || typeof x !== 'object' || depth > 5) return;
    if (x.upgrade_bag) {
      const ref = x.instance_reference || x.instanceReference || x.pbgid || keyHint;
      if (ref) map.set(refTail(ref), x);
      if (keyHint) map.set(keyHint, x);
    }
    if (Array.isArray(x)) return x.forEach(v => walk(v, '', depth + 1));
    for (const [k, v] of Object.entries(x)) if (v && typeof v === 'object') walk(v, k, depth + 1);
  }
  walk(data);
  return map;
}
async function firstWorkingIcon(paths) {
  const candidates = [];
  for (const p0 of paths) {
    const p = normalizeIconPath(p0);
    if (!p) continue;
    candidates.push(p);
    const flat = p.split('/').pop();
    candidates.push(`export_flatten/${flat}`);
  }
  for (const rel of [...new Set(candidates)]) {
    const url = `${CDN_RAW_ROOT}/${rel}`;
    const buf = await getBinary(url);
    if (buf?.length) return { rel, url, buf };
  }
  return null;
}

function patchIndex(html, manifest) {
  html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);

  const manifestConst = `const BATTLEGROUP_ICON_PATHS=${JSON.stringify(manifest)};\n`;
  if (/const COH3_DATA_BASES=/.test(html)) {
    html = html.replace(/const COH3_DATA_BASES=[\s\S]*?const ENEMIES=/, `${manifestConst}const ENEMIES=`);
  } else if (/const BATTLEGROUP_ICON_PATHS=/.test(html)) {
    html = html.replace(/const BATTLEGROUP_ICON_PATHS=.*?;\n/, manifestConst);
  } else {
    html = html.replace(/const BATTLEGROUP_RECOMMENDATIONS=.*?;\n/, m => `${m}${manifestConst}`);
  }

  const start = html.indexOf('function iconNodeKey(');
  const end = html.indexOf('function renderBattlegroupTree(', start);
  if (start < 0 || end < 0) throw new Error('Could not locate battlegroup icon/render helper block in index.html');
  const localHelpers = `function iconNodeKey(branchName,tierIndex,choice){return \`${'${branchName}|${tierIndex}|${choice}'}\`}\nfunction battlegroupIconKey(p,branchName,tierIndex,choice){return \`${'${p.faction}|${p.battlegroup}|${branchName}|${tierIndex}|${choice}'}\`}\nfunction renderTreeNode(p,branchName,tierIndex,choice,selectionMap){const sel=selectionMap[\`${'${branchName}|${tierIndex}|${choice}'}\`],src=BATTLEGROUP_ICON_PATHS[battlegroupIconKey(p,branchName,tierIndex,choice)]||'';return \`<div class="bg-node${'${sel?\' selected\':\'\'}'}">${'${sel?.step?`<span class="bg-step">${sel.step}</span>`:\'\'}'}${'${src?`<span class="bg-icon-slot loaded"><img class="bg-icon" src="${escapeHtml(src)}" alt="" loading="lazy"></span>`:\'\'}'}<div class="bg-node-label">${'${escapeHtml(choice)}'}</div></div>\`}\nfunction renderTierRow(p,branchName,tier,tierIndex,selectionMap){const opts=tier.options||[];if(opts.length===1)return \`<div class="bg-tier-row count-1"><div class="bg-node-shell">${'${renderTreeNode(p,branchName,tierIndex,opts[0],selectionMap)}'}</div></div>\`;return \`<div class="bg-tier-row count-2"><div class="bg-node-shell">${'${renderTreeNode(p,branchName,tierIndex,opts[0],selectionMap)}'}</div><div></div><div class="bg-node-shell">${'${renderTreeNode(p,branchName,tierIndex,opts[1],selectionMap)}'}</div></div>\`}\nfunction renderConnectorRow(fromTier,toTier){const a=(fromTier.options||[]).length,b=(toTier.options||[]).length;let parts='';if(a===1&&b===1)parts='<span class="bg-line center-full"></span>';else if(a===1&&b===2)parts='<span class="bg-line center-top"></span><span class="bg-line bridge"></span><span class="bg-line left-bottom"></span><span class="bg-line right-bottom"></span>';else if(a===2&&b===1)parts='<span class="bg-line left-top"></span><span class="bg-line right-top"></span><span class="bg-line bridge"></span><span class="bg-line center-bottom"></span>';else if(a===2&&b===2)parts='<span class="bg-line left-top"></span><span class="bg-line right-top"></span><span class="bg-line bridge"></span><span class="bg-line left-bottom"></span><span class="bg-line right-bottom"></span>';return \`<div class="bg-connector">${'${parts}'}</div>\`}\nfunction renderBranchTree(p,branch,selectionMap){return \`<div class="bg-branch-card"><div class="bg-branch-title">${'${escapeHtml(branch.name)}'}</div><div class="bg-branch-diagram">${'${branch.tiers.map((tier,i)=>`${renderTierRow(p,branch.name,tier,i,selectionMap)}${i<branch.tiers.length-1?renderConnectorRow(tier,branch.tiers[i+1]):\'\'}`).join(\'\')}'}</div></div>\`}\n`;
  html = html.slice(0, start) + localHelpers + html.slice(end);

  html = html.replace(/function renderBattlegroupTree\(p\)\{[\s\S]*?\nfunction renderUnlockRecommendation\(p\)/,
    `function renderBattlegroupTree(p){const tree=battlegroupTreeFor(p),schema=validateBattlegroupTree(tree);if(!schema.ok)return \`<div class="notice"><strong>Tree data error:</strong> \${schema.errors.join(' ')}</div>\`;const selectionMap=recommendationSelectionMap(p),hasSelected=Object.keys(selectionMap).length>0;return \`<div class="bg-tree-intro">Visual battlegroup tree for <strong>\${escapeHtml(p.battlegroup)}</strong>. Ability icons are served locally from this GitHub Pages site, so the tree does not depend on a third-party icon request at runtime. Recommended choices are highlighted and numbered where a stored order exists.</div><div class="bg-tree-key"><span class="bg-tree-pill"><span class="bg-tree-dot neutral"></span>Legal ability node</span><span class="bg-tree-pill"><span class="bg-tree-dot selected"></span>Recommended node</span>\${hasSelected?'<span class="bg-tree-pill"><span class="bg-tree-dot numbered"></span>Yellow badge = pick order</span>':''}</div><div class="bg-tree-wrap" style="margin-top:12px">\${tree.branches.map(branch=>renderBranchTree(p,branch,selectionMap)).join('')}</div>\`}\nfunction renderUnlockRecommendation(p)`);

  html = html.replace(/;hydrateBattlegroupIcons\(p,\$\("advisorContent"\)\)/g, ';');
  html = html.replace(/;hydrateBattlegroupIcons\(p,\$\("matchContent"\)\)/g, ';');

  if (!html.includes('.bg-tier-row.count-1 .bg-node-shell{grid-column:2')) {
    html = html.replace('.bg-node-shell{width:100%;display:flex;justify-content:center}', '.bg-node-shell{width:100%;display:flex;justify-content:center}.bg-tier-row.count-1 .bg-node-shell{grid-column:2;width:100%}');
  }
  html = html.replace(/\.bg-icon-fallback\{[^}]*\}/g, '.bg-icon-fallback{display:none}');
  html = html.replace(/\.bg-icon-slot\.failed \.bg-icon-fallback\{[^}]*\}/g, '');
  return html;
}

async function main() {
  const data = JSON.parse(await fs.readFile(JSON_PATH, 'utf8'));
  const trees = data.battlegroupTrees || {};
  const battlegroupData = await getJson(`${DATA_ROOT}/battlegroup.json`);
  const upgradeByFaction = {};
  for (const [faction, race] of Object.entries(RACE_KEYS)) {
    upgradeByFaction[faction] = indexRecords(await getJson(`${DATA_ROOT}/chunked/upgrade/${race}.json`));
  }

  await fs.mkdir(ASSET_DIR, { recursive: true });
  const manifest = {};
  const report = { dataTag: DATA_TAG, generatedAt: new Date().toISOString(), resolved: [], unresolved: [] };

  for (const [faction, bgs] of Object.entries(trees)) {
    const race = RACE_KEYS[faction];
    const raceBgs = battlegroupData?.races?.[race] || {};
    for (const [bg, tree] of Object.entries(bgs)) {
      const rawKey = resolveRawBattlegroupKey(faction, bg, raceBgs);
      const rawBg = rawKey ? raceBgs[rawKey] : null;
      const rawBranches = rawBg?.techtree_bag?.branches || [];
      for (let bi = 0; bi < tree.branches.length; bi++) {
        const branch = tree.branches[bi];
        const refs = (rawBranches[bi]?.branch?.upgrades || []).map(x => x?.upgrade?.instance_reference).filter(Boolean);
        const choices = branch.tiers.flatMap(t => t.options || []);
        const paired = matchChoicesToRefs(choices, refs);
        for (let ti = 0; ti < branch.tiers.length; ti++) {
          for (const choice of branch.tiers[ti].options || []) {
            const fullKey = keyFor(faction, bg, branch.name, ti, choice);
            const override = ICON_OVERRIDES[fullKey];
            const ref = paired[choice];
            const rec = ref ? upgradeByFaction[faction].get(refTail(ref)) : null;
            const candidates = [override, ...extractIconNames(rec)].filter(Boolean);
            const found = await firstWorkingIcon(candidates);
            if (!found) {
              report.unresolved.push({ key: fullKey, rawBattlegroupKey: rawKey, ref: ref || null, candidates });
              continue;
            }
            const filename = outputName(faction, bg, branch.name, ti, choice);
            const outPath = path.posix.join(ASSET_DIR, filename);
            await fs.writeFile(outPath, found.buf);
            manifest[fullKey] = outPath;
            report.resolved.push({ key: fullKey, path: outPath, upstream: found.rel, ref: ref || null });
          }
        }
      }
    }
  }

  await fs.writeFile(MANIFEST_PATH, JSON.stringify(manifest, null, 2) + '\n');
  await fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + '\n');

  const totalNodes = Object.values(trees).reduce((sum, bgs) => sum + Object.values(bgs).reduce((s, tree) => s + tree.branches.reduce((z, branch) => z + branch.tiers.reduce((q, tier) => q + tier.options.length, 0), 0), 0), 0);
  console.log(`Resolved ${report.resolved.length}/${totalNodes} battlegroup nodes; unresolved ${report.unresolved.length}.`);
  if (report.unresolved.length) {
    console.error('Unresolved icon nodes:');
    for (const x of report.unresolved) console.error(` - ${x.key} (ref: ${x.ref || 'none'})`);
    throw new Error(`Icon sync incomplete: ${report.unresolved.length} nodes unresolved.`);
  }

  let html = await fs.readFile(HTML_PATH, 'utf8');
  html = patchIndex(html, manifest);
  await fs.writeFile(HTML_PATH, html);

  data.verified = `10 Sep 2026 — ${VERSION} local battlegroup icon asset update. All canonical battlegroup-tree ability icons are copied into this repository under assets/icons and referenced by same-origin paths in index.html. The site no longer depends on runtime COH3 Stats icon metadata/CDN requests for the visual battlegroup tree. Current client patch is 2.5.5; cached CoHDB ranking/map/statistical rows collected on 2.5.3 remain explicitly labelled as snapshots.`;
  await fs.writeFile(JSON_PATH, JSON.stringify(data, null, 2) + '\n');
}

main().catch(err => { console.error(err); process.exit(1); });
