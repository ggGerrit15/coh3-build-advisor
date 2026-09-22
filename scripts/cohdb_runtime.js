const COHDB_MODE_KEYS = {'1v1': '1v1', '2v2': '2v2', '3v3': '3v3', '4v4': '4v4'};
const COHDB_RATING_KEYS = {'Under 1000': 'Under 1000', '1000-1200': '1000 – 1200', '1200-1400': '1200 – 1400', '1400-1600': '1400 – 1600', '1600-1800': '1600 – 1800', '1800+': '1800+'};
function cohdbModeKey(value) { return COHDB_MODE_KEYS[value] || 'all'; }
function cohdbRatingKey(value) { return COHDB_RATING_KEYS[value] || value; }
function cohdbBattlegroupStat(p) { return (COHDB_SNAPSHOT?.battlegroups || []).find(x => x.faction === p.faction && x.battlegroup === p.battlegroup && x.mode === 'all' && x.rating_filter === 'balanced_all') || null; }
function cohdbStepKey(value) { return normalizeBuildIconToken(String(value || '').replace(/\bconstruct\b/ig, ' ').replace(/\b(?:squad|team|vehicle|tank|car|gun)\b/ig, ' ').replace(/\banti[- ]tank\b/ig, ' at ').replace(/\bmachine gun\b/ig, ' mg ')); }
function cohdbStepMatches(a, b) { const x = cohdbStepKey(a), y = cohdbStepKey(b); return !!x && !!y && (x === y || x.includes(y) || y.includes(x)); }
function cohdbArchetypeFor(p) {
  const candidates = (COHDB_SNAPSHOT?.build_orders || []).filter(x => x.faction === p.faction);
  if (!candidates.length) return null;
  const profileSteps = (p.build || []).filter(x => !/^\[SCOUT\]/i.test(x));
  return candidates.map(source => {
    const sourceSteps = [...(source.most_common_and_variants || [])].flatMap(x => (x.steps || []).map(y => y.name));
    const hits = profileSteps.filter(step => sourceSteps.some(candidate => cohdbStepMatches(step, candidate))).length;
    const maximum = Math.max(1, Math.min(profileSteps.length, sourceSteps.length));
    const alignment = Math.min(hits, maximum) / maximum;
    return {source, alignment, hits};
  }).sort((a, b) => b.alignment - a.alignment || (b.source.mode_summaries?.all?.games || 0) - (a.source.mode_summaries?.all?.games || 0))[0] || null;
}
function cohdbComponent(p) {
  const bgStat = cohdbBattlegroupStat(p);
  const family = (COHDB_SNAPSHOT?.battlegroups || []).filter(x => x.faction === p.faction && x.mode === 'all' && x.rating_filter === 'balanced_all');
  const familyAvg = family.length ? family.reduce((sum, x) => sum + x.win_rate, 0) / family.length : 50;
  let bonus = 0;
  if (bgStat) {
    bonus += clamp((bgStat.win_rate - familyAvg) * 0.12, -2.5, 2.5);
    if (bgStat.selections < 150) bonus -= 0.75;
    else if (bgStat.selections < 300) bonus -= 0.25;
    else if (bgStat.selections >= 1000) bonus += 0.25;
  }
  const archetype = cohdbArchetypeFor(p);
  const modeStat = archetype?.source?.mode_summaries?.[cohdbModeKey(p.mode)] || null;
  const ratingStat = archetype?.source?.rating_bands?.[cohdbModeKey(p.mode)]?.[cohdbRatingKey(elo.value)] || null;
  if (archetype?.alignment >= 0.25) bonus += clamp((archetype.alignment - 0.25) * 3, 0, 2);
  return {bonus: clamp(bonus, -3, 4), bgStat, familyAvg, archetype, modeStat, ratingStat};
}
function cohdbStatsSection(p) {
  const c = cohdbComponent(p), bgStat = c.bgStat, a = c.archetype, modeStat = c.modeStat, ratingStat = c.ratingStat;
  if (!bgStat && !a) return '';
  const source = a?.source, sourceLabel = source ? `${source.title} · ${source.faction}` : '';
  return `<div class="card"><h3>Imported CoHDB evidence</h3><div class="statline">${bgStat ? `<div class="statpill"><div class="statnum">${bgStat.win_rate.toFixed(1)}%</div><div class="small muted">Battlegroup all modes</div><div class="small muted">n=${bgStat.selections.toLocaleString()}</div></div>` : ''}${modeStat ? `<div class="statpill"><div class="statnum">${modeStat.win_rate.toFixed(1)}%</div><div class="small muted">${p.mode} archetype</div><div class="small muted">n=${modeStat.games.toLocaleString()}</div></div>` : ''}${ratingStat ? `<div class="statpill"><div class="statnum">${ratingStat.win_rate.toFixed(1)}%</div><div class="small muted">${elo.value} archetype</div><div class="small muted">n=${ratingStat.games.toLocaleString()}</div></div>` : ''}</div>${source ? `<p class="small muted" style="margin-top:9px"><strong>Matched CoHDB archetype:</strong> ${escapeHtml(sourceLabel)}${a.hits ? ` · ${a.hits} matching core steps` : ''}. This is faction-level build evidence, not a battlegroup-specific win rate.</p><p class="small muted">The imported CoHDB signal contributes only a small amount to the Smart Advisor score; the curated profile, matchup logic and technical QA remain primary.</p><a href="${source.source_url}" target="_blank" rel="noopener noreferrer">Open imported CoHDB build ↗</a>` : ''}</div>`;
}
