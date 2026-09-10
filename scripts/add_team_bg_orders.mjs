import fs from 'node:fs/promises';

const JSON_PATH = 'coh3_build_advisor_data.json';
const HTML_PATH = 'index.html';
const VERSION = 'v1.1.10';

// Team-game battlegroup baseline. Each plan starts from the already-reviewed
// small-game selection for every legal branch/tier, then applies only the
// listed team-game choice swaps and a legal cross-branch pick order.
// Branch references use canonical tree order: "0:1" = branch 1, tier 1.
const PLANS = {
  Wehrmacht: {
    'Breakthrough': {
      '3v3': { order:['0:1','1:1','0:2','0:3','1:2','1:3'], choices:{'1:1':'2.5-tonne Cargo Truck'} },
      '4v4': { order:['0:1','0:2','1:1','0:3','1:2','1:3'], choices:{'1:1':'2.5-tonne Cargo Truck'} },
    },
    'Italian Coastal': {
      '3v3': { order:['1:1','0:1','1:2','0:2','1:3','0:3'], choices:{'0:1':'Support Bunkers','0:2':'Designated Artillery Overwatch','0:3':'Bulwark','1:3':'Obice da 210/22'} },
      '4v4': { order:['0:1','1:1','1:2','0:2','1:3','0:3'], choices:{'0:1':'Support Bunkers','0:2':'Designated Artillery Overwatch','0:3':'Bulwark','1:3':'Obice da 210/22'} },
    },
    'Last Stand': {
      '3v3': { order:['1:1','1:2','0:1','0:2','1:3','0:3'] },
      '4v4': { order:['1:1','1:2','0:1','1:3','0:2','0:3'], choices:{'1:3':'Immobilize and Fortify'} },
    },
    'Luftwaffe': {
      '3v3': { order:['1:1','0:1','0:2','1:2','1:3','0:3'], choices:{'1:2':'Flak 38 Anti-Air Emplacement'} },
      '4v4': { order:['1:1','0:1','0:2','1:2','0:3','1:3'], choices:{'1:2':'Flak 38 Anti-Air Emplacement','1:3':'Flak 36 Anti-tank Emplacement'} },
    },
    'Mechanized': {
      '3v3': { order:['0:1','0:2','1:1','1:2','0:3','1:3'], choices:{'0:2':'StuG Assault Group','1:1':'Spotting Scopes'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'0:2':'StuG Assault Group','1:1':'Spotting Scopes'} },
    },
    'Siege Breaker': {
      '3v3': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'0:2':'Construct Siege Camp'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'0:2':'Construct Siege Camp','0:3':'Sturmtiger production unlock'} },
    },
    'Terror': {
      '3v3': { order:['1:1','0:1','1:2','0:2','0:3','1:3'] },
      '4v4': { order:['1:1','1:2','0:1','0:2','1:3','0:3'] },
    },
  },
  USF: {
    'Advanced Infantry': {
      '3v3': { order:['1:1','0:1','0:2','1:2','0:3','1:3'], choices:{'1:1':'Ammunition Storage','0:2':'Frontline Medical Station','0:3':'Infantry Assault'} },
      '4v4': { order:['1:1','1:2','0:1','0:2','1:3','0:3'], choices:{'1:1':'Ammunition Storage','0:2':'Frontline Medical Station','0:3':'Infantry Assault'} },
    },
    'Airborne': {
      '3v3': { order:['1:1','1:2','0:1','0:2','1:3','0:3'], choices:{'1:1':'Heavy Machine Gun Paradrop','0:3':'Carpet Bombing Run'} },
      '4v4': { order:['1:1','0:1','1:2','0:2','1:3','0:3'], choices:{'1:1':'Heavy Machine Gun Paradrop','0:3':'Carpet Bombing Run'} },
    },
    'Armored': {
      '3v3': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'1:1':'Strength in Steel'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'1:1':'Strength in Steel','0:3':'M31 Recovery Vehicle'} },
    },
    'Free French': {
      '3v3': { order:['1:1','0:1','0:2','0:3','1:2','1:3'] },
      '4v4': { order:['1:1','0:1','0:2','1:2','0:3','1:3'] },
    },
    'Heavy Weapons': {
      '3v3': { order:['0:1','1:1','1:2','0:2','0:3','1:3'], choices:{'1:2':'Halftrack Strongpoints'} },
      '4v4': { order:['0:1','1:1','1:2','0:2','0:3','1:3'], choices:{'1:2':'Halftrack Strongpoints','0:3':'Black Dragon Artillery Barrage','1:3':'M26 Pershing'} },
    },
    'Italian Partisan': {
      '3v3': { order:['0:1','1:1','1:2','0:2','0:3','1:3'] },
      '4v4': { order:['0:1','0:2','1:1','1:2','0:3','1:3'] },
    },
    'Special Operations': {
      '3v3': { order:['0:1','1:1','1:2','0:2','0:3','1:3'], choices:{'0:1':'M29 Weasel with M1 Pack Howitzer','1:1':'Raiding Flares'} },
      '4v4': { order:['0:1','1:1','1:2','0:2','0:3','1:3'], choices:{'0:1':'M29 Weasel with M1 Pack Howitzer','1:1':'Raiding Flares'} },
    },
  },
  British: {
    'Air and Sea': {
      '3v3': { order:['0:1','1:1','1:2','0:2','0:3','1:3'] },
      '4v4': { order:['1:1','1:2','0:1','0:2','0:3','1:3'] },
    },
    'Australian Defense': {
      '3v3': { order:['1:1','0:1','0:2','1:2','1:3','0:3'], choices:{'0:1':'Strengthen Economy','1:2':'Defensive Tactics'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','1:3','0:3'], choices:{'0:1':'Strengthen Economy','1:2':'Defensive Tactics'} },
    },
    'Canadian Shock': {
      '3v3': { order:['0:1','0:2','1:1','1:2','0:3','1:3'] },
      '4v4': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'0:3':'Smoke Operation'} },
    },
    'Heavy Armor': {
      '3v3': { order:['1:1','0:1','1:2','0:2','1:3','0:3'] },
      '4v4': { order:['1:1','0:1','1:2','0:2','1:3','0:3'], choices:{'1:2':'Radio Net'} },
    },
    'Indian Artillery': {
      '3v3': { order:['1:1','0:1','0:2','1:2','0:3','1:3'] },
      '4v4': { order:['1:1','1:2','0:1','0:2','1:3','0:3'] },
    },
    'Polish Cavalry': {
      '3v3': { order:['0:1','1:1','0:2','0:3','1:2','1:3'] },
      '4v4': { order:['1:1','0:1','1:2','0:2','0:3','1:3'] },
    },
    'Special Service': {
      '3v3': { order:['0:1','1:1','0:2','1:2','0:3','1:3'] },
      '4v4': { order:['1:1','0:1','0:2','1:2','0:3','1:3'] },
    },
  },
  DAK: {
    'Armored Support': {
      '3v3': { order:['0:1','1:1','0:2','1:2','1:3','0:3'], choices:{'0:3':'Stuka Anti-tank Loiter'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','1:3','0:3'], choices:{'0:3':'Stuka Anti-tank Loiter'} },
    },
    'Elite Forces': {
      '3v3': { order:['0:1','0:2','1:1','1:2','0:3','1:3'], choices:{'0:2':'Daring Assault'} },
      '4v4': { order:['0:1','1:1','0:2','1:2','0:3','1:3'], choices:{'0:2':'Daring Assault'} },
    },
    'Italian Combined Arms': {
      '3v3': { order:['0:1','1:1','0:2','1:2','0:3','1:3'] },
      '4v4': { order:['0:1','1:1','0:2','0:3','1:2','1:3'], choices:{'1:3':'Artillery Cover'} },
    },
    'Italian Infantry': {
      '3v3': { order:['1:1','0:1','1:2','0:2','1:3','0:3'] },
      '4v4': { order:['1:1','0:1','0:2','1:2','0:3','1:3'] },
    },
    'Kriegsmarine': {
      '3v3': { order:['0:1','1:1','1:2','1:3','0:2','0:3'] },
      '4v4': { order:['0:1','1:1','1:2','1:3','0:2','0:3'] },
    },
    'Panzerjäger Kommand': {
      '3v3': { order:['1:1','0:1','1:2','0:2','0:3','1:3'], choices:{'1:3':'Elefant'} },
      '4v4': { order:['1:1','0:1','1:2','0:2','0:3','1:3'], choices:{'1:3':'Elefant'} },
    },
    'Battlefield Espionage': {
      '3v3': { order:['0:1','1:1','1:2','0:2','1:3','0:3'] },
      '4v4': { order:['1:1','0:1','1:2','1:3','0:2','0:3'] },
    },
  },
};

function clone(x) { return JSON.parse(JSON.stringify(x)); }
function tokenParts(token) {
  const [b,t] = token.split(':').map(Number);
  if (!Number.isInteger(b) || !Number.isInteger(t)) throw new Error(`Bad plan token: ${token}`);
  return { b, t };
}
function smallChoiceMap(small) {
  const out = new Map();
  for (const step of small.sequence || []) out.set(`${step.branch}|${step.tier}`, step.choice);
  return out;
}
function buildSequence(tree, small, plan) {
  const existing = smallChoiceMap(small);
  const sequence = [];
  for (const token of plan.order) {
    const { b, t } = tokenParts(token);
    const branch = tree.branches?.[b];
    const tier = branch?.tiers?.[t-1];
    if (!branch || !tier) throw new Error(`Unknown ${token} in ${tree?.source || 'tree'}`);
    const override = plan.choices?.[token];
    const fallback = existing.get(`${branch.name}|${t}`) || tier.options?.[0];
    const choice = override || fallback;
    sequence.push({ branch: branch.name, tier: t, choice });
  }
  return sequence;
}
function validateSequence(tree, sequence, label) {
  if (!tree?.branches?.length) throw new Error(`${label}: missing canonical tree`);
  if (sequence.length !== 6) throw new Error(`${label}: expected 6 picks, got ${sequence.length}`);
  const expectedTier = Object.fromEntries(tree.branches.map(b => [b.name,1]));
  const seen = new Set();
  for (let i=0;i<sequence.length;i++) {
    const s = sequence[i];
    const branch = tree.branches.find(b => b.name === s.branch);
    if (!branch) throw new Error(`${label} #${i+1}: unknown branch ${s.branch}`);
    const tier = branch.tiers[s.tier-1];
    if (!tier) throw new Error(`${label} #${i+1}: invalid tier ${s.tier}`);
    const key = `${s.branch}|${s.tier}`;
    if (seen.has(key)) throw new Error(`${label} #${i+1}: duplicate ${key}`);
    seen.add(key);
    if (!tier.options.includes(s.choice)) throw new Error(`${label} #${i+1}: illegal choice ${s.choice} for ${key}`);
    if (s.tier !== expectedTier[s.branch]) throw new Error(`${label} #${i+1}: ${s.branch} tier ${s.tier} skips tier ${expectedTier[s.branch]}`);
    expectedTier[s.branch] += 1;
  }
  for (const branch of tree.branches) {
    if (expectedTier[branch.name] !== branch.tiers.length + 1) throw new Error(`${label}: did not complete ${branch.name}`);
  }
}

const data = JSON.parse(await fs.readFile(JSON_PATH,'utf8'));
const recs = data.battlegroupRecommendations || {};
const trees = data.battlegroupTrees || {};
let bgCount = 0;
let orderCount = 0;

for (const [faction,bgs] of Object.entries(recs)) {
  for (const [bg, bucket] of Object.entries(bgs)) {
    bgCount += 1;
    const small = bucket.small;
    const tree = trees?.[faction]?.[bg];
    const plan = PLANS?.[faction]?.[bg];
    if (!small?.sequence?.length) throw new Error(`${faction}|${bg}: missing small recommendation sequence`);
    if (!tree) throw new Error(`${faction}|${bg}: missing canonical tree`);
    if (!plan?.['3v3'] || !plan?.['4v4']) throw new Error(`${faction}|${bg}: missing explicit 3v3/4v4 team plan`);

    for (const mode of ['3v3','4v4']) {
      const modePlan = plan[mode];
      const sequence = buildSequence(tree, small, modePlan);
      validateSequence(tree, sequence, `${faction}|${bg}|${mode}`);
      bucket[mode] = {
        label: `${mode} team-game battlegroup order`,
        scope: `${mode} team-game baseline`,
        confidence: modePlan.confidence || small.confidence || 'Medium',
        sequence,
        notes: [],
        evidence: 'Team-game baseline built from the project’s Havoc Patch 2.5 feedback, existing team-game role notes, and the canonical Patch 2.5.5 battlegroup tree. Exact mode entries are kept separate from the 1v1/2v2 small-game baseline.',
      };
      orderCount += 1;
    }
    delete bucket.team;
  }
}

const plannedBgs = Object.values(PLANS).reduce((sum,bgs)=>sum+Object.keys(bgs).length,0);
if (bgCount !== 28) throw new Error(`Expected 28 battlegroups in recommendation data, found ${bgCount}`);
if (plannedBgs !== 28) throw new Error(`Expected 28 battlegroups in team plan config, found ${plannedBgs}`);
if (orderCount !== 56) throw new Error(`Expected 56 team-game orders, generated ${orderCount}`);

data.verified = `10 Sep 2026 — ${VERSION} team-game battlegroup order update. Added explicit, canonical-tree-validated 3v3 and 4v4 numbered battlegroup recommendations for all 28 battlegroups (56 team-game orders total). Team modes no longer fall through to a missing generic team recommendation; the frontend now resolves exact 3v3/4v4 entries before any fallback. Existing 1v1/2v2 small-game recommendations remain unchanged.`;
await fs.writeFile(JSON_PATH, JSON.stringify(data,null,2)+'\n');

let html = await fs.readFile(HTML_PATH,'utf8');
html = html.replace(/CoH3 Build Advisor v1\.1\.\d+/g, `CoH3 Build Advisor ${VERSION}`);
await fs.writeFile(HTML_PATH, html);

console.log(`Added and validated ${orderCount} team-game battlegroup orders across ${bgCount} battlegroups.`);
