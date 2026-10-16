import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const page = fs.readFileSync('index.html', 'utf8');

const inlineScripts = [...page.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)]
  .filter(([, attrs, body]) => !/\bsrc\s*=/.test(attrs) && body.trim());
assert.ok(inlineScripts.length > 0, 'page should include an inline application script');
for (const [index, [, attrs, body]] of inlineScripts.entries()) {
  assert.doesNotThrow(() => new vm.Script(body), 'inline script ' + index + ' should parse');
}


function extractFunction(name) {
  const start = page.indexOf('function ' + name + '(');
  assert.ok(start >= 0, 'missing function ' + name);
  // Let the JS parser handle nested template interpolation, regexes and comments.
  // The first closing brace yielding a complete declaration is the boundary.
  for (let end = page.indexOf('}', start); end >= 0; end = page.indexOf('}', end + 1)) {
    const source = page.slice(start, end + 1);
    try { new vm.Script(source); return source; } catch (error) {
      if (!(error instanceof SyntaxError)) throw error;
    }
  }
  throw new Error('unterminated function ' + name);
}

function extractConstant(name) {
  const marker = 'const ' + name + ' =';
  const start = page.indexOf(marker);
  assert.ok(start >= 0, 'missing constant ' + name);
  const valueStart = start + marker.length;
  const end = page.indexOf(';', valueStart);
  assert.ok(end > valueStart, 'unterminated constant ' + name);
  return new Function('return (' + page.slice(valueStart, end).trim() + ');')();
}

const modeKeys = extractConstant('COHDB_MODE_KEYS');
const ratingFilters = extractConstant('COHDB_RAW_RATING_FILTERS');
const modeChoices = new Function('PROFILES', 'uniq', extractFunction('modeOptions') + '; return modeOptions("DAK");')(
  ['1v1', '2v2', '3v3', '4v4'].map(mode => ({faction: 'DAK', mode})),
  values => [...new Set(values)]
);
assert.equal(modeChoices[0], 'All Modes');
assert.deepEqual(modeChoices.slice(1).sort(), ['1v1', '2v2', '3v3', '4v4']);
assert.ok(extractFunction('refreshMain').includes('options(mode,modeOptions(fac.value))'));
assert.ok(extractFunction('refreshRankControls').includes('options(rmode,modeOptions(rfac.value))'));
const simulateRefreshMain = (previousMode, availableModes) => {
  const faction = {value: 'USF'};
  const mode = {value: previousMode, options: []};
  const setOptions = (element, values) => {
    element.options = values.map(value => ({value}));
    element.value = values[0];
  };
  const refreshMain = new Function(
    'fac', 'mode', 'options', 'modeOptions', 'refreshBG',
    extractFunction('refreshMain') + '\nreturn refreshMain;'
  )(faction, mode, setOptions, () => availableModes, () => {});
  refreshMain();
  return mode.value;
};
assert.equal(
  simulateRefreshMain('3v3', ['All Modes', '1v1', '2v2', '3v3', '4v4']),
  '3v3',
  'changing faction should preserve a still-available 3v3 selection'
);
assert.equal(
  simulateRefreshMain('4v4', ['All Modes', '1v1', '2v2']),
  'All Modes',
  'changing faction should fall back to All Modes if the previous mode is unavailable'
);

const patchId = 'test-patch';
const rates = [
  ['avg_under_1000', 1, 9],
  ['avg_1000_1200', 90, 10],
  ['avg_1200_1400', 6, 4],
  ['avg_1400_1600', 7, 3],
  ['avg_1600_1800', 8, 2],
  ['avg_1800_plus', 9, 1]
];

function bgRows(name, mode, wins, losses) {
  return rates.map(([rating_filter], i) => ({
    faction: 'DAK',
    battlegroup: name,
    mode,
    rating_filter,
    map: 'all',
    opponent: 'all',
    patch: {id: patchId},
    wins: typeof wins === 'function' ? wins(i) : wins,
    losses: typeof losses === 'function' ? losses(i) : losses
  }));
}

const snapshot = {
  patch: {id: patchId, label: 'test patch'},
  battlegroups: [
    ...bgRows('Kriegsmarine', 'all', i => rates[i][1], i => rates[i][2]),
    ...bgRows('Mechanized', 'all', 1, 9),
    ...bgRows('Kriegsmarine', '1v1', 10000, 0),
    {
      faction: 'DAK', battlegroup: 'Kriegsmarine', mode: 'all',
      rating_filter: 'balanced_all', map: 'all', opponent: 'all',
      patch: {id: patchId}, wins: 53, losses: 47
    },
    {
      faction: 'DAK', battlegroup: 'Kriegsmarine', mode: 'all',
      rating_filter: 'avg_under_1000', map: 'specific-map', opponent: 'all',
      patch: {id: patchId}, wins: 10000, losses: 0
    }
  ]
};

const functions = [
  extractFunction('cohdbModeKey'),
  extractFunction('cohdbScopeFor'),
  extractFunction('cohdbRawRowsFor'),
  extractFunction('cohdbAggregateRows'),
  extractFunction('cohdbRatingFilterForBand'),
  extractFunction('cohdbRatingStat'),
  extractFunction('cohdbModeBattlegroups'),
  extractFunction('cohdbModeAllRatingsStat'),
  extractFunction('factionEloAvg'),
  extractFunction('exactModeComponent')
].join('\n');

const stats = new Function(
  'COHDB_SNAPSHOT', 'COHDB_MODE_KEYS', 'COHDB_RAW_RATING_FILTERS', 'clamp',
  functions + '\nreturn {cohdbModeKey,cohdbScopeFor,cohdbRatingStat,cohdbModeBattlegroups,factionEloAvg,exactModeComponent};'
)(snapshot, modeKeys, ratingFilters, (x, min, max) => Math.max(min, Math.min(max, x)));

const profile = {faction: 'DAK', battlegroup: 'Kriegsmarine', mode: 'All Modes'};
const pooled = stats.cohdbRatingStat(profile, 'All Ratings');
assert.equal(stats.cohdbModeKey('All Modes'), 'all');
assert.deepEqual(stats.cohdbScopeFor(profile), {mode: 'all', map: 'all', opponent: 'all', patch: patchId});
assert.equal(pooled.wins, 121);
assert.equal(pooled.losses, 29);
assert.equal(pooled.n, 150);
assert.equal(pooled.coverage, 6);
assert.equal(pooled.complete, true);
assert.ok(Math.abs(pooled.wr - (121 / 150 * 100)) < 1e-9);
assert.equal(stats.cohdbModeBattlegroups('DAK', 'All Modes').length, 2);
assert.ok(Math.abs(stats.factionEloAvg('DAK', 'All Ratings', 'All Modes') - (127 / 210 * 100)) < 1e-9);
assert.equal(stats.exactModeComponent(profile).bonus, 4);

const partialSnapshot = {...snapshot, battlegroups: snapshot.battlegroups.filter(
  row => !(row.battlegroup === 'Kriegsmarine' && row.mode === 'all' && row.rating_filter === 'avg_1800_plus')
)};
const partialStats = new Function(
  'COHDB_SNAPSHOT', 'COHDB_MODE_KEYS', 'COHDB_RAW_RATING_FILTERS', 'clamp',
  functions + '\nreturn {cohdbRatingStat};'
)(partialSnapshot, modeKeys, ratingFilters, (x, min, max) => Math.max(min, Math.min(max, x)));
const partial = partialStats.cohdbRatingStat(profile, 'All Ratings');
assert.equal(partial.coverage, 5);
assert.equal(partial.complete, false);

const scoreSource = extractFunction('scoreProfile');
const safeScoreSource = extractFunction('safeScoreValue');
const score = new Function(
  'averageMatchupComponent', 'eloComponent', 'exactModeComponent',
  'recoveryComponent', 'confidenceBonus', 'cohdbComponent',
  'clamp', 'safeScoreValue',
  safeScoreSource + '\n' + scoreSource + '\nreturn scoreProfile;'
)(
  () => ({laneRank: 1, bonus: 10}),
  () => ({bonus: 2}),
  () => ({bonus: 1}),
  () => 3,
  () => 9,
  p => ({bonus: p.cohdbBonus ?? Number.NaN}),
  (x, min, max) => Math.max(min, Math.min(max, x)),
  (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback
);
const exactModeScore = score({faction: 'DAK', battlegroup: 'Kriegsmarine', mode: '1v1', confidence: 'High'}, 'All Ratings');
assert.equal(exactModeScore.score, 80);
assert.equal(exactModeScore.cohdb, 0);
assert.equal('map' in exactModeScore, false);
const allModesScore = score({
  ...profile,
  averageConfidence: 6,
  modeProfiles: [
    {cohdbBonus: 2}, {cohdbBonus: 4}, {cohdbBonus: 6}, {cohdbBonus: 8}
  ]
}, 'All Ratings');
assert.equal(allModesScore.score, 82);
assert.equal(allModesScore.cohdb, 5);
assert.equal('map' in allModesScore, false);

console.log('Current embedded CoHDB statistics and All Modes scoring checks passed.');

// Creator guides number production separately from the squad already on the field.
// Keep source facts outside the renderer, so a missing U1 or mistaken unit name
// cannot silently become the new expectation when the frontend is edited.
const advisorData = JSON.parse(fs.readFileSync('coh3_build_advisor_data.json', 'utf8'));
const creatorAudit = JSON.parse(fs.readFileSync('data/creator-build-audit.json', 'utf8'));
const embeddedCreators = JSON.parse(page.match(/const CREATOR_BUILDS=(.*);\n/)[1]);
assert.deepEqual(embeddedCreators, advisorData.creatorBuilds, 'live creator data must match the editable data file');
const auditKey = x => `${x.creator}|${x.faction}|${x.battlegroup}|${x.title}`;
assert.deepEqual(
  creatorAudit.entries.map(auditKey).sort(),
  advisorData.creatorBuilds.map(auditKey).sort(),
  'audit must account for every saved creator entry'
);
const creatorFunctions = [
  'normalizeDisplayUnit', 'starterFromDisplay', 'displayBuildSteps',
  'escapeHtml', 'creatorBuildItems', 'creatorBuildHtml', 'creatorPhaseChoices',
  'creatorMiniCard', 'normalizeStep', 'compareCandidates', 'updateCompare',
  'phaseBuild', 'buildStepInfo', 'buildHtml', 'renderBuildVisualizer'
].map(extractFunction).join('\n');
const compareDetail = {innerHTML: ''};
let comparisonProfile;
const creatorRuntime = new Function(
  'CREATOR_BUILDS', 'PATCH', 'currentProfile', 'effectiveBuild', '$', 'requestAnimationFrame',
  creatorFunctions + '\nreturn {displayBuildSteps,creatorBuildItems,creatorMiniCard,normalizeStep,updateCompare,renderBuildVisualizer};'
)(embeddedCreators, advisorData.patch, () => comparisonProfile, p => p.build, () => compareDetail, () => {});
const sourceUnitKey = value => value.replace(/^(?:2nd|3rd|second|third)\s+/i, '').toLowerCase();
const guideEntries = advisorData.creatorBuilds.filter(c => c.unitNumbering === 'U');
assert.equal(guideEntries.length, creatorAudit.guideReceipts.length);
for (const source of creatorAudit.guideReceipts) {
  const c = guideEntries.find(x => auditKey(x) === auditKey(source));
  assert.ok(c, `missing audited guide ${source.sourceTitle}`);
  assert.equal(c.sourcePatch, source.sourcePatch);
  assert.equal(c.sourceUrl, source.videoUrl);
  assert.equal(c.build.length, source.unitSlots.length + 1, 'START must not consume a source U slot');
  const items = creatorRuntime.creatorBuildItems(c);
  assert.equal(items[0].label, 'START');
  for (const [i, slot] of source.unitSlots.entries()) {
    assert.equal(items[i + 1].label, slot.label);
    assert.equal(sourceUnitKey(items[i + 1].text), sourceUnitKey(slot.unit), `${source.sourceTitle} ${slot.label}`);
  }
  assert.match(items[1].text, /^2nd /, 'U1 must retain the additional Pioneer or Engineer');
  assert.deepEqual(c.phaseChoices, source.phaseSlots, 'P milestones must stay separate from unit production');
  const choiceKey = value => value.toLowerCase().replace(/production unlock:?|medium tank|heavy tank/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  assert.deepEqual(c.path.map(choiceKey), source.battlegroupSelections.map(choiceKey));
  const tree = advisorData.battlegroupTrees[c.faction][c.battlegroup];
  const progress = new Map(tree.branches.map(branch => [branch.name, 0]));
  for (const choice of c.path) {
    const matches = tree.branches.flatMap(branch => branch.tiers.flatMap((tier, i) =>
      tier.options.some(option => choiceKey(option) === choiceKey(choice)) ? [{branch, tier: i + 1}] : []
    ));
    assert.equal(matches.length, 1, `unknown or ambiguous BG choice ${choice}`);
    const match = matches[0];
    assert.equal(match.tier, progress.get(match.branch.name) + 1, 'default path must respect prerequisites and exclusive choices');
    progress.set(match.branch.name, match.tier);
  }
  const card = creatorRuntime.creatorMiniCard(c);
  assert.match(card, /<strong>START:<\/strong>/);
  assert.match(card, /<strong>U1:<\/strong> 2nd /);
  assert.match(card, /<strong>U10:<\/strong>/);
  assert.doesNotMatch(card, /<strong>U11:<\/strong>/);
  assert.match(card, /Buildings, upgrades and other choices/);
  assert.ok(card.includes(c.sourceUrl), 'checked guide must be directly reviewable');
  // Exercise the comparison surface too; it must not reintroduce the old U1 loss.
  comparisonProfile = {faction: c.faction, battlegroup: c.battlegroup, mode: '1v1', build: ['Starting unit: ' + items[0].text]};
  const candidates = embeddedCreators.filter(x => x.faction === c.faction && x.battlegroup === c.battlegroup && x.modes.includes('1v1'));
  creatorRuntime.updateCompare(candidates.findIndex(x => auditKey(x) === auditKey(c)));
  assert.match(compareDetail.innerHTML, /<strong>U1:<\/strong> 2nd /);
  const visual = creatorRuntime.renderBuildVisualizer(c.build, c);
  assert.equal((visual.match(/buildstepbadge start/g) || []).length, 1);
  assert.match(visual, /buildstepbadge ">1<\/div>/, 'first produced unit must be step 1 in visual cards');
}
const pureLuftwaffe = guideEntries.find(c => c.battlegroup === 'Luftwaffe');
assert.match(pureLuftwaffe.build[7], /^LG40 /);
assert.ok(!JSON.stringify(pureLuftwaffe.build).includes('Pak 40'));
assert.ok(!pureLuftwaffe.notes.some(note => note.startsWith('Pak 40:')));
assert.equal(creatorRuntime.normalizeStep('Start: Pioneer'), creatorRuntime.normalizeStep('Starting unit: Pioneer'));
const triplePioneer = advisorData.creatorBuilds.find(c => c.title.includes('triple-Pioneer'));
assert.deepEqual(creatorRuntime.displayBuildSteps(triplePioneer.build).slice(0, 3), ['Starting unit: Pioneer', '2nd Pioneer', '3rd Pioneer']);
const airborne = advisorData.creatorBuilds.find(c => c.creator === 'Havoc' && c.battlegroup === 'Airborne');
assert.deepEqual(creatorRuntime.displayBuildSteps(airborne.build).slice(0, 2), ['Starting unit: Scout', '2nd Scout']);
const incomplete = advisorData.creatorBuilds.find(c => c.creator === 'Stephen' && c.battlegroup === 'Terror');
assert.ok(creatorRuntime.creatorBuildItems(incomplete).every(x => !x.label), 'an incomplete replay recap must not acquire invented U labels');
console.log('Creator source slots, starting units, legal default BG paths and both display surfaces passed.');
