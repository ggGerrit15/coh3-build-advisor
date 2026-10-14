use cohlib::{extract_build_order, parse_replay, BuildActionKind, Faction, VersionedStore};
use flate2::read::GzDecoder;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, error::Error, fs, io, io::Read, path::PathBuf};

const COHLIB_REV: &str = "d31ade03fa69301c571ceb7416d0d1e67eff99aa";
const MAX_REPLAY_BYTES: u64 = 128 * 1024 * 1024;

fn replay_bytes(input: &[u8]) -> Result<Vec<u8>, Box<dyn Error>> {
    if input.len() as u64 > MAX_REPLAY_BYTES {
        return Err("Replay exceeds the 128 MiB input limit".into());
    }
    if input.starts_with(&[0x1f, 0x8b]) {
        let mut bytes = Vec::new();
        GzDecoder::new(input)
            .take(MAX_REPLAY_BYTES + 1)
            .read_to_end(&mut bytes)?;
        if bytes.len() as u64 > MAX_REPLAY_BYTES {
            return Err("Decompressed replay exceeds the 128 MiB limit".into());
        }
        Ok(bytes)
    } else {
        Ok(input.to_vec())
    }
}

fn faction_name(faction: Faction) -> &'static str {
    match faction {
        Faction::Americans => "USF",
        Faction::British => "British",
        Faction::Wehrmacht => "Wehrmacht",
        Faction::AfrikaKorps => "DAK",
    }
}

fn action_kind(kind: &BuildActionKind) -> &'static str {
    match kind {
        BuildActionKind::ConstructBuilding => "construct_building",
        BuildActionKind::TrainUnit => "train_unit",
        BuildActionKind::ResearchUpgrade => "research_upgrade",
        BuildActionKind::SelectBattlegroup => "select_battlegroup",
        BuildActionKind::SelectBattlegroupAbility => "select_battlegroup_ability",
        BuildActionKind::UseBattlegroupAbility => "use_battlegroup_ability",
        BuildActionKind::AITakeover => "ai_takeover",
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let mut args = env::args_os().skip(1);
    let path = args
        .next()
        .map(PathBuf::from)
        .ok_or("Usage: coh3-replay-reader FILE.rec")?;
    if args.next().is_some() {
        return Err("Usage: coh3-replay-reader FILE.rec".into());
    }
    let size = fs::metadata(&path)?.len();
    if size > MAX_REPLAY_BYTES {
        return Err("Replay exceeds the 128 MiB input limit".into());
    }
    let input = fs::read(path)?;
    let bytes = replay_bytes(&input)?;
    let replay = parse_replay(&bytes)?;
    let store = VersionedStore::bundled();
    let build = u32::from(replay.version());
    let exact_data = store.builds().contains(&build);
    let mut players = Vec::new();
    for (index, player) in replay.players().iter().enumerate() {
        // Keep cancelled and suspect commands visible for later review. They are
        // excluded from the usable build sequence by the Python normalizer.
        let order = extract_build_order(&replay, index, &store, true)?;
        let actions: Vec<Value> = order
            .actions
            .iter()
            .map(|action| {
                let name = store.local_name_for_formatted(action.pbgid, build);
                json!({
                    "tick": action.tick,
                    "seconds": f64::from(action.tick) / 8.0,
                    "command_index": action.index,
                    "kind": action_kind(&action.kind),
                    "pbgid": action.pbgid,
                    "name": name,
                    "name_resolved": name.is_some(),
                    "cancelled": action.cancelled,
                    "suspect": action.suspect_since.is_some(),
                    "suspect_since_tick": action.suspect_since,
                })
            })
            .collect();
        let bg = player.battlegroup();
        players.push(json!({
            "player_index": index,
            "profile_id": player.profile_id(),
            "name": player.name(),
            "human": player.human(),
            "faction": faction_name(player.faction()),
            "team": player.team().value(),
            "battlegroup": bg.map(|id| json!({
                "pbgid": id,
                "name": store.local_name_for_formatted(id, build),
                "selected_at_tick": player.battlegroup_selected_at(),
            })),
            "ai_takeover_at_tick": player.ai_takeover_at(),
            "actions": actions,
        }));
    }
    let result = json!({
        "schema_version": "coh3.replay-reader.v1",
        "parser": {
            "name": "coh3-replay-reader",
            "version": env!("CARGO_PKG_VERSION"),
            "cohlib_revision": COHLIB_REV,
            "exact_game_data_available": exact_data,
            "names_may_use_version_fallback": true,
        },
        "replay_sha256": format!("{:x}", Sha256::digest(&bytes)),
        "match": {
            "match_id": replay.matchhistory_id(),
            "game_build": build,
            "patch": store.semver_string_for(build),
            "game_type": format!("{:?}", replay.game_type()),
            "mod_uuid": replay.mod_uuid().to_string(),
            "map": replay.map_filename(),
            "recorded_at_local": replay.timestamp(),
            "duration_seconds": replay.length() as f64 / 8.0,
        },
        "players": players,
    });
    serde_json::to_writer_pretty(io::stdout().lock(), &result)?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("Replay reader failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{write::GzEncoder, Compression};
    use std::io::Write;

    #[test]
    fn gzip_and_plain_files_have_the_same_replay_bytes() {
        let source = b"CoH3 replay bytes";
        let mut writer = GzEncoder::new(Vec::new(), Compression::default());
        writer.write_all(source).unwrap();
        assert_eq!(replay_bytes(&writer.finish().unwrap()).unwrap(), source);
        assert_eq!(replay_bytes(source).unwrap(), source);
    }

    #[test]
    fn corrupt_gzip_is_rejected() {
        assert!(replay_bytes(&[0x1f, 0x8b, 0]).is_err());
    }
}
