import assert from 'node:assert/strict';
import fs from 'node:fs';

const runtime = fs.readFileSync('scripts/cohdb_runtime.js', 'utf8');
const normalizeBuildIconToken = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[character]));

function makeSnapshot(ratingGames) {
  return {
    battlegroups: [
      {
        faction: 'DAK',
        battlegroup: 'Kriegsmarine',
        mode: 'all',
        rating_filter: 'balanced_all',
        win_rate: 52.8,
        selections: 2884
      },
      {
        faction: 'DAK',
        battlegroup: 'Kriegsmarine',
        mode: '1v1',
        rating_filter: 'avg_1600_1800',
        wins: Math.ceil(ratingGames * 0.6),
        losses: ratingGames - Math.ceil(ratingGames * 0.6),
        win_rate: Number((Math.ceil(ratingGames * 0.6) * 100 / ratingGames).toFixed(1)),
        selections: ratingGames
      }
    ],
    build_orders: [{
      faction: 'DAK',
      title: 'Mechanized',
      source_url: 'https://cohdb.com/build_orders/afrika_korps/mechanized',
      most_common_and_variants: [{steps: [{name: 'Kriegsmariner'}]}],
      mode_summaries: {'1v1': {win_rate: 49.8, games: 269}},
      rating_bands: {'1v1': {'1600 – 1800': {win_rate: 72.7, games: ratingGames}}}
    }]
  };
}

function loadRuntime(snapshot) {
  return new Function(
    'COHDB_SNAPSHOT',
    'normalizeBuildIconToken',
    'clamp',
    'elo',
    'escapeHtml',
    `${runtime}\nreturn {cohdbComponent, cohdbStatsSection, cohdbSelectedBattlegroupStat};`
  )(snapshot, normalizeBuildIconToken, clamp, {value: '1600-1800'}, escapeHtml);
}

const profile = {
  faction: 'DAK',
  battlegroup: 'Kriegsmarine',
  mode: '1v1',
  build: ['Kriegsmariner']
};

const sparse = loadRuntime(makeSnapshot(11));
const sparseComponent = sparse.cohdbComponent(profile);
assert.equal(sparseComponent.ratingEvidence.status, 'sparse');
assert.equal(sparseComponent.ratingEvidence.usable, false);
const sparseMarkup = sparse.cohdbStatsSection(profile);
assert.match(sparseMarkup, /Zu kleine Stichprobe/);
assert.match(sparseMarkup, />—<\/div>/);
assert.doesNotMatch(sparseMarkup, /72\.7%/);

const weak = loadRuntime(makeSnapshot(30));
const weakComponent = weak.cohdbComponent(profile);
assert.equal(weakComponent.ratingEvidence.status, 'weak');
assert.equal(weakComponent.ratingEvidence.usable, true);
assert.match(weak.cohdbStatsSection(profile), /55\.0%|72\.7%/);
assert.match(weak.cohdbStatsSection(profile), /Schwache Evidenz/);

const selectedCohort = weak.cohdbComponent(profile).selectedBgStat;
assert.equal(selectedCohort.rating_filter, 'avg_1600_1800');
assert.equal(selectedCohort.selections, 30);
assert.match(weak.cohdbStatsSection(profile), /1v1 battlegroup · 1600-1800/);
assert.match(weak.cohdbStatsSection(profile), /60\.0%/);
assert.match(weak.cohdbStatsSection(profile), /Record 18–12/);

const missingSnapshot = makeSnapshot(30);
missingSnapshot.battlegroups = missingSnapshot.battlegroups.filter(row => row.mode === 'all');
const missing = loadRuntime(missingSnapshot);
assert.equal(missing.cohdbSelectedBattlegroupStat(profile), null);
assert.match(missing.cohdbStatsSection(profile), /CoHDB did not report this battlegroup for this filter/);

console.log('CoHDB mode/rating runtime checks passed.');
