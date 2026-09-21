import fs from 'node:fs/promises';

const DATA_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const README_PATH = 'README.md';
const ICON_MANIFEST_PATH = 'assets/build-icons.json';
const VERSION = 'v1.1.30';
const CLIENT_PATCH = '2.5.6';

function replaceEmbeddedConstant(html, name, value) {
  const pattern = new RegExp(`const ${name}=.*?;\\n`, 's');
  if (!pattern.test(html)) throw new Error(`Embedded ${name} block not found`);
  return html.replace(pattern, `const ${name}=${JSON.stringify(value)};\n`);
}

const data = JSON.parse(await fs.readFile(DATA_PATH, 'utf8'));
const profile = (data.profiles || []).find(
  p => p.faction === 'DAK' && p.battlegroup === 'Kriegsmarine' && p.mode === '1v1'
);

if (!profile) throw new Error('Missing DAK Kriegsmarine 1v1 profile');

profile.confidence = 'Medium';
profile.verdict =
  'Open with two Kriegsmariners and an early 250, then use Panzerjäger plus a real scouting fork: 8 Rad for uncontested anti-infantry tempo, or Pak 38 into Marder against a fast Stuart or Greyhound.';
profile.build = [
  'Starting unit: Panzerpioneer',
  'Kriegsmariner',
  'Kriegsmariner',
  '250 Light Carrier',
  'Kriegsmariner',
  'Light Support Kompanie',
  'Panzerjäger',
  'Fire Support Elements',
  '[SCOUT] Stuart / Greyhound tech',
  'Mechanized Kompanie',
  '8 Rad if no fast enemy light vehicle',
  'Support Armor Elements',
  'StuG III D',
  'Marder III',
  '254 Recon Tractor',
  'Marder III / StuG III D according to enemy composition'
];
profile.target = [
  'Panzerpioneer',
  '2–3 Kriegsmariners',
  '250 Light Carrier',
  'Panzerjäger',
  '8 Rad versus infantry or Pak 38 + Marder versus Allied light vehicles',
  'StuG III D when anti-infantry armor is needed',
  '254 Recon Tractor',
  '1–2 Marders as enemy armor scales'
];
profile.tips = [
  'Use the 250 as a transport, combined-arms and healing platform; preserve it instead of taking frontal vehicle fights.',
  'Place one early Hardpoint on a safe, useful fuel or munitions point once 50 munitions are available; improve it before expanding to more points.',
  'The 8 Rad is not the answer to a Stuart. Panzerjäger buys time, while Pak 38 and Marder provide the hard anti-vehicle layer.'
];
profile.branches = [
  [
    'Motor Pool or Stuart tech is likely',
    'After Fire Support Elements: Pak 38 → Mechanized Kompanie → Marder III; delay or skip the 8 Rad',
    'A Stuart or Greyhound can punish an uncovered 8-Rad timing.'
  ],
  [
    'Stuart / Greyhound is already fielded',
    'Pak 38 immediately, Panzerjäger screening in front, then Mechanized → Marder III',
    'Do not try to solve the vehicle with an unsupported 8 Rad.'
  ],
  [
    'No early enemy light-vehicle tech',
    'Mechanized → 8 Rad → Support Armor → StuG III D; add Marder as enemy armor appears',
    'This converts the safe opening into anti-infantry map pressure.'
  ],
  [
    'First 50 munitions after two Kriegs + 250',
    'Designate one safe fuel or munitions point as the first Hardpoint; then Improved Hardpoints → Supply Interdiction',
    'One defensible point starts the logistics value without wasting munitions on exposed structures.'
  ],
  [
    'Manpower is tight before the first tech',
    'Delay the third Kriegsmariner; if necessary, skip the 250 rather than delaying all tech and anti-LV coverage',
    'The 250 is the preferred default, not an unconditional tax.'
  ],
  [
    'Behind or fuel-starved',
    'Stabilize with Panzerjäger + Pak 38 and 250 healing before Support Armor / StuG investment',
    'Field safety matters more than forcing the planned vehicle timing.'
  ]
];
profile.variants = [
  {
    name: '250 → 8 Rad tempo',
    when: 'No fast Motor Pool / Stuart timing is showing',
    build: [
      'Panzerpioneer',
      'Kriegsmariner ×2',
      '250 Light Carrier',
      'Kriegsmariner #3',
      'Light Support Kompanie',
      'Panzerjäger',
      'Fire Support Elements',
      'Mechanized Kompanie',
      '8 Rad',
      'Support Armor Elements',
      'StuG III D',
      'Marder III'
    ],
    note: 'The 8 Rad is the anti-infantry tempo choice only after scouting confirms that it will not have to duel the first Allied light vehicle.'
  },
  {
    name: 'Pak 38 → Marder safety',
    when: 'USF Motor Pool or British Stuart tech is likely / confirmed',
    build: [
      'Panzerpioneer',
      'Kriegsmariner ×2',
      '250 Light Carrier',
      'Light Support Kompanie',
      'Panzerjäger',
      'Fire Support Elements',
      'Pak 38',
      'Mechanized Kompanie',
      'Marder III',
      'StuG III D only after anti-vehicle safety'
    ],
    note: 'Delay the third Kriegsmariner or 8 Rad when needed; Pak 38 plus Marder is the reliable answer to the first Stuart/Greyhound window.'
  }
];
profile.evidence = [
  'HelpingHans Kriegsmarine guide transcript directly supports an early 250, two Kriegsmariners and an early safe Hardpoint.',
  'CoHDB current statistical patch 2.5.5 shows the 250 in recurring DAK Fire Support / Mechanized variants; those archetypes are faction-level, not Kriegsmarine-specific.',
  'CoH3Stats production data supports Panzerjäger from Light Support, Pak 38 after Fire Support Elements, and Marder III from Mechanized Kompanie.',
  'Official client Hot Fix 2.5.6 changed a Final Stand exploit only and did not announce multiplayer balance changes.'
];
profile.techQaNotes = [
  'Panzerjäger is available from the Light Support Kompanie. Fire Support Elements unlocks the Pak 38 branch used against Stuart/Greyhound pressure.',
  'Marder III is produced from the Mechanized Kompanie; Support Armor Elements unlocks StuG III D and is not treated as the anti-vehicle prerequisite.',
  'The 8 Rad branch is explicitly conditional and must not be used as the sole answer to a Stuart.'
];
profile.techQa =
  'Patch 2.5.6 production legality checked; the hotfix did not change multiplayer balance or this tech route';

const kriegsmarineTree = data.battlegroupTrees?.DAK?.Kriegsmarine;
if (!kriegsmarineTree) throw new Error('Missing canonical DAK Kriegsmarine tree');
kriegsmarineTree.verifiedPatch = CLIENT_PATCH;
kriegsmarineTree.source =
  'CoH3Stats DAK Explorer / cohstats open battlegroup data; rechecked after the official 2.5.6 hotfix, which did not alter multiplayer balance or the battlegroup tree.';

const smallRecommendation = data.battlegroupRecommendations?.DAK?.Kriegsmarine?.small;
if (!smallRecommendation) throw new Error('Missing DAK Kriegsmarine small-game recommendation');
smallRecommendation.label = 'Early Hardpoint logistics priority';
smallRecommendation.notes = [
  'Unlock Kriegsmariners first, then prioritize Designate Resupply Point before Starburst Flares.',
  'Place the first 50-munition Hardpoint on a safe, useful fuel or munitions point after the two-Kriegsmariner + 250 opening; do not spam exposed points.',
  'Improved Hardpoints must come before Supply Interdiction in the recommended logistics sequence.',
  'Starburst Flares and Naval Intervention are later utility choices; Stuka Overflight and Fritz X remain situational alternatives.'
];
smallRecommendation.evidence =
  'HelpingHans Kriegsmarine guide evidence plus Havoc feedback, reconciled with the canonical tree and the official 2.5.6 no-balance hotfix.';

data.patch = CLIENT_PATCH;
data.verified =
  '21 Sep 2026 — v1.1.30 Kriegsmarine 1v1 update. Added the early 250 opening, explicit Hardpoint timing, and a scout-dependent 8 Rad versus Pak 38/Marder branch for Stuart and Greyhound pressure. Client patch 2.5.6 made no multiplayer balance changes; CoHDB statistical layers remain labelled by their source patch.';

const hotfixSource = (data.sources || []).find(source => source.name === 'Official Hot Fix 2.5.5');
if (hotfixSource) {
  hotfixSource.name = 'Official Hot Fix 2.5.6';
  hotfixSource.note =
    'Current client-version verification. Hot Fix 2.5.6 fixed a Final Stand perk exploit and did not announce multiplayer balance or battlegroup-tree changes.';
}

const iconManifest = JSON.parse(await fs.readFile(ICON_MANIFEST_PATH, 'utf8'));
const carrierIcon = iconManifest['DAK|250 half track'] || 'assets/build-icons/dak--250-half-track.webp';
iconManifest['DAK|250 light carrier'] = carrierIcon;

await fs.writeFile(DATA_PATH, JSON.stringify(data, null, 2) + '\n');
await fs.writeFile(ICON_MANIFEST_PATH, JSON.stringify(iconManifest, null, 2) + '\n');

let html = await fs.readFile(HTML_PATH, 'utf8');
html = replaceEmbeddedConstant(html, 'PROFILES', data.profiles);
html = replaceEmbeddedConstant(html, 'SOURCES', data.sources);
html = replaceEmbeddedConstant(html, 'BATTLEGROUP_TREES', data.battlegroupTrees);
html = replaceEmbeddedConstant(html, 'BATTLEGROUP_RECOMMENDATIONS', data.battlegroupRecommendations);
html = replaceEmbeddedConstant(html, 'PATCH', data.patch);
html = replaceEmbeddedConstant(html, 'BUILD_ORDER_ICON_PATHS', iconManifest);
html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
html = html.replace(
  'The current client patch is 2.5.5 as of 10 Sep 2026. Hot Fix 2.5.5 addressed the artillery barrage cooldown exploit and logging and did not announce battlegroup-tree changes.',
  'The current client patch is 2.5.6 as of 21 Sep 2026. Hot Fix 2.5.6 fixed a Final Stand perk exploit and did not announce multiplayer balance or battlegroup-tree changes. CoHDB still labels 2.5.5 as its latest statistical patch because the 2.5.6 hotfix contained no balance changes.'
);
html = html.replace(
  '<div class="goodnotice" style="margin-top:10px"><strong>v1.1.4 icon-loading fix:</strong>',
  '<div class="goodnotice" style="margin-top:10px"><strong>v1.1.30 Kriegsmarine 1v1 update:</strong> The default opening now uses two Kriegsmariners into an early 250, then a third Kriegsmariner when manpower permits. After Panzerjäger and Fire Support Elements, the build branches: 8 Rad only without fast Allied light-vehicle tech; Pak 38 into Marder against Stuart/Greyhound pressure. The battlegroup advice also shows when to place the first safe Hardpoint.<br><br><strong>v1.1.4 icon-loading fix:</strong>'
);
await fs.writeFile(HTML_PATH, html);

let readme = await fs.readFile(README_PATH, 'utf8');
readme = readme.replace(/\*\*v\d+\.\d+\.\d+ — (?:Client )?Patch [^*]+\*\*/, `**${VERSION} — Client Patch ${CLIENT_PATCH}**`);
await fs.writeFile(README_PATH, readme);

console.log(`Updated DAK Kriegsmarine 1v1 profile and synchronized ${VERSION}.`);
