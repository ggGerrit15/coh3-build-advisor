-- SQLite research store. Raw observations and their sources are never overwritten.
PRAGMA application_id = 1129269299;
PRAGMA user_version = 1;

CREATE TABLE sources (
    source_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('cohort', 'upload', 'single_replay')),
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE matches (
    match_id INTEGER PRIMARY KEY CHECK (match_id > 0),
    game_build INTEGER NOT NULL,
    patch TEXT,
    mode TEXT,
    map TEXT NOT NULL,
    mod_uuid TEXT,
    duration_seconds REAL NOT NULL CHECK (duration_seconds >= 0),
    core_sha256 TEXT NOT NULL
);

CREATE TABLE replays (
    replay_sha256 TEXT PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    raw_game_type TEXT,
    recorded_at_local TEXT,
    parser_json TEXT NOT NULL
);

CREATE TABLE match_players (
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    profile_id INTEGER NOT NULL CHECK (profile_id > 0),
    name TEXT NOT NULL,
    faction TEXT NOT NULL,
    battlegroup TEXT,
    team INTEGER NOT NULL,
    human INTEGER NOT NULL CHECK (human IN (0, 1)),
    ai_takeover_at_tick INTEGER,
    opponent_factions_json TEXT NOT NULL,
    PRIMARY KEY (match_id, profile_id)
);

CREATE TABLE datasets (
    dataset_sha256 TEXT PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(match_id),
    replay_sha256 TEXT NOT NULL REFERENCES replays(replay_sha256),
    source_url TEXT,
    payload_json TEXT NOT NULL,
    first_imported_at TEXT NOT NULL,
    UNIQUE (dataset_sha256, match_id)
);

CREATE TABLE source_datasets (
    source_key TEXT NOT NULL REFERENCES sources(source_key),
    dataset_sha256 TEXT NOT NULL REFERENCES datasets(dataset_sha256),
    input_name TEXT NOT NULL,
    PRIMARY KEY (source_key, dataset_sha256, input_name)
);

CREATE TABLE player_evidence (
    dataset_sha256 TEXT NOT NULL,
    match_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    rating_before REAL,
    rating_before_unverified REAL,
    displayed_rating REAL,
    rating_status TEXT NOT NULL CHECK (rating_status IN ('verified_pre_match', 'source_claim', 'unverified', 'unknown')),
    result TEXT CHECK (result IN ('win', 'loss', 'draw')),
    result_status TEXT NOT NULL CHECK (result_status IN ('matched_daily_source', 'observed_source', 'unknown')),
    ranked_eligible INTEGER NOT NULL CHECK (ranked_eligible IN (0, 1)),
    opener5_usable INTEGER NOT NULL CHECK (opener5_usable IN (0, 1)),
    opener8_usable INTEGER NOT NULL CHECK (opener8_usable IN (0, 1)),
    quality_checks_json TEXT NOT NULL,
    match_type_resolution_json TEXT NOT NULL,
    PRIMARY KEY (dataset_sha256, profile_id),
    FOREIGN KEY (dataset_sha256, match_id) REFERENCES datasets(dataset_sha256, match_id),
    FOREIGN KEY (match_id, profile_id) REFERENCES match_players(match_id, profile_id)
);

CREATE TABLE actions (
    match_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    event_index INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    command_index INTEGER NOT NULL,
    kind TEXT NOT NULL,
    pbgid INTEGER NOT NULL,
    name TEXT,
    cancelled INTEGER NOT NULL CHECK (cancelled IN (0, 1)),
    suspect INTEGER NOT NULL CHECK (suspect IN (0, 1)),
    name_resolved INTEGER NOT NULL CHECK (name_resolved IN (0, 1)),
    excluded_reasons_json TEXT NOT NULL,
    build_position INTEGER,
    bg_unlock_position INTEGER,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (match_id, profile_id, event_index),
    FOREIGN KEY (match_id, profile_id) REFERENCES match_players(match_id, profile_id)
);

CREATE INDEX idx_players_scope ON match_players(faction, battlegroup, match_id);
CREATE INDEX idx_matches_scope ON matches(patch, mode);
CREATE INDEX idx_actions_build ON actions(match_id, profile_id, build_position);
CREATE INDEX idx_evidence_player ON player_evidence(match_id, profile_id);

CREATE VIEW v_best_player_evidence AS
SELECT * FROM (
    SELECT e.*, ROW_NUMBER() OVER (
        PARTITION BY match_id, profile_id
        ORDER BY (rating_status = 'verified_pre_match') DESC,
                 (result_status = 'matched_daily_source') DESC,
                 (result IS NOT NULL) DESC, ranked_eligible DESC, dataset_sha256
    ) AS evidence_rank
    FROM player_evidence e
) WHERE evidence_rank = 1;

CREATE VIEW v_player_builds AS
SELECT m.match_id, m.patch, m.game_build, m.mode, m.map, m.duration_seconds,
       p.profile_id, p.name, p.faction, p.battlegroup, p.opponent_factions_json,
       p.human, p.ai_takeover_at_tick, e.dataset_sha256,
       e.rating_before, e.rating_status,
       CASE WHEN e.rating_status = 'verified_pre_match' THEN e.rating_before END AS verified_rating_before,
       e.result, e.result_status, e.ranked_eligible, e.opener5_usable, e.opener8_usable,
       e.quality_checks_json, e.match_type_resolution_json
FROM matches m JOIN match_players p USING (match_id)
JOIN v_best_player_evidence e USING (match_id, profile_id);

CREATE VIEW v_battlegroup_coverage AS
SELECT patch, mode, faction, battlegroup, COUNT(*) AS player_games,
       COUNT(DISTINCT profile_id) AS distinct_players,
       SUM(opener5_usable) AS usable_first5, SUM(opener8_usable) AS usable_first8,
       SUM(rating_status = 'verified_pre_match') AS verified_ratings,
       SUM(ranked_eligible AND opener8_usable AND rating_status = 'verified_pre_match') AS eligible_ladder_first8
FROM v_player_builds GROUP BY patch, mode, faction, battlegroup;

CREATE VIEW v_build_commands AS
SELECT a.match_id, a.profile_id, a.build_position, a.tick / 8.0 AS seconds,
       a.kind, a.pbgid, a.name, b.patch, b.mode, b.faction, b.battlegroup,
       b.opponent_factions_json, b.verified_rating_before, b.result, b.ranked_eligible
FROM actions a JOIN v_player_builds b USING (match_id, profile_id)
WHERE a.build_position IS NOT NULL;
