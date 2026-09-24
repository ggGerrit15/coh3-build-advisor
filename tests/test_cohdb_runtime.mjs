import assert from 'node:assert/strict';
import fs from 'node:fs';

const page = fs.readFileSync('index.html', 'utf8');

function extractFunction(name) {
  const start = page.indexOf('function ' + name + '(');
  assert.ok(start >= 0, 'missing function ' + name);
  const open = page.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let i = open; i < page.length; i += 1) {
    const ch = page[i];
    const next = page[i + 1];
    if (lineComment) {
      if (ch === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') { blockComment = false; i += 1; }
      continue;
    }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') { lineComment = true; i += 1; continue; }
    if (ch === '/' && next === '*') { blockComment = true; i += 1; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return page.slice(start, i + 1);
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
