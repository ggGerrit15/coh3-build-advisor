# Creator build transcription audit — 16 October 2026

This pass checks the saved creator library against recovered source material.
It does not update historical builds to the current balance patch, certify every
conditional shorthand as a complete production queue, or change the synthesized
Current Advisor profiles.

## Corrections checked against the original guides

Three 3HappyDolphin entries were checked against their public **Patch 2.5.3**
guide editions. The source dates and patch stay historical even though this
audit was performed in October.

| Guide | Corrections |
| --- | --- |
| [Pure Luftwaffe](https://youtu.be/7gC-RSsFGio) | Keep the starting Pioneer and restore the additional Pioneer at U1. U7 is LG40 Recoilless Gun Paradrop, not Pak 40. U10 defaults to Brummbär, with Panzer IV as the vehicle-pressure alternative. Remove the unsupported Kettenkrad side choice from this edition's U1 and correct the camouflage note to refer to LG40. |
| [Siege Breaker](https://youtu.be/w1zPwr9BBJs) | Restore the additional Pioneer at U1. Replace the wrongly transcribed fifth BG choice, Siege Camp, with Designate Siege Leader. Keep Panzer IV as the default U10; Brummbär is the follow-up alternative if Panzer IV was selected at U9. Repair Pioneer is a side choice. |
| [Heavy Armor](https://youtu.be/ANQVav1BMBE) | Keep the starting Royal Engineer and restore the additional Engineer at U1. Preserve U2–U10 and move the late Crusader gun conversion into its upgrade note instead of inventing an extra unit slot. |

The three entries now show **START**, then **U1–U10**. Their building, upgrade
and other **P** milestones are shown separately. Main and side choices retain
the source grouping; a P row is not itself a strict unlock sequence. The
numbered battlegroup path supplies that order. Siege Camp/Grinding Advance and
Sturmtiger/Siege Leader remain alternatives, never cumulative default purchases.

The source's BG path and unit slots were read from the published guide payload
at `https://trainer.3happydolphin.com/api/build-guides`.
[Audit records](../data/creator-build-audit.json) retain the selected guide IDs,
patch, video URLs, a SHA-256 of each rendered source guide, and extracted factual
U/P/BG names. They contain no private pipeline material or email text.

## Review of all 19 saved entries

“Transcript reviewed” means the stated core and relevant branches were
corroborated in the original supplied transcript. These flexible recaps have
not been converted into invented exact queues. “Partial replay” means the
narration cannot establish the complete opening. Two entries still lack a
recoverable original source; neither is marked source-verified.

| Creator | Saved entry | Review result |
| --- | --- | --- |
| Havoc | Luftwaffe T2 tempo | Transcript reviewed: 221, optional Flak 30, Fallschirmjäger, LG40 and support-tech core. |
| Havoc | Luftwaffe T3 | Transcript reviewed: 251 conversion, Fallschirmjäger, Pak and Officer Quarters guidance. |
| Havoc | Mechanized small-game | Transcript reviewed: triple-Pioneer means three total, including the starting squad. |
| Havoc | Mechanized team-game | Transcript reviewed: Ketten/MG/Gren opening, fuel-dependent Pak/PGren choice and Panther transition. |
| Havoc | Breakthrough T2 tempo | Transcript reviewed: additional Pioneer, triple Gren, MP40, Rapid Production and 221 core. |
| Tightrope | Breakthrough Tiger macro | Original video/notes unavailable in this pass; saved sequence retained. |
| Tightrope | Siege Leader Wirbelwind | Original transcript checked at 14:40–16:07; starting and produced Pioneer are separate. |
| Tightrope | Flame 251 → Brummbär | Original transcript checked at 16:10–17:19. This guide converts a normal 251; it is not the different Dolphin direct-251/16 route. |
| Stephen | Siege Breaker vs USF | Partial replay: PGren/Pak, Siege Camp and armor core corroborated; full initial queue not established. |
| Stephen | Terror attrition | Partial replay: the recording explicitly missed the opening. Keep the recap without inventing START/U1. |
| Helping Hans | Kriegsmarine opener | Transcript reviewed: immediate Kriegsmariner alongside 250, second Kriegsmariner and light/fire-support route. BG list is priorities, not a complete prerequisite path. |
| Havoc | Saved four-Kriegsmariner shorthand | Original source and CP order unavailable; implicit tech/start are not invented. |
| Havoc | Italian Infantry | Transcript reviewed: bike/extra Pioneer/250, double-Panzerjäger revision and 259 conversion. |
| Havoc | Airborne | Transcript reviewed: two Scouts total, including the starting Scout; two paradrop MGs, Engineer and M3/GMC route. |
| Havoc | Free French vs Wehrmacht | Transcript reviewed: Sections/Jeep, conditional mortar, Mechanized support and Motor Pool route. |
| Havoc | Free French vs DAK | Transcript reviewed: WSC team-game opening and early support vehicles; later tech stays adaptive. |
| 3HappyDolphin | Heavy Armor | Guide checked: U1–U10, P milestones and selected BG path; corrected as above. |
| 3HappyDolphin | Siege Breaker | Guide checked: U1–U10, P milestones and selected BG path; corrected as above. |
| 3HappyDolphin | Pure Luftwaffe | Guide checked: U1–U10, P milestones and selected BG path; corrected as above. |

Other creator sequences are unchanged by this pass. In particular, a source
requiring a second Pioneer/Scout is not normalized down to a starting unit,
and a partial replay recap is not assigned an exact production order.

## Regression checks

`node tests/test_cohdb_runtime.mjs` checks editable/live creator-data parity,
START versus U1 on the library and comparison surfaces, source unit-slot
alignment, separate P rows, and legal prerequisite/exclusive choices for the
three corrected default BG paths. It also covers the existing triple-Pioneer
and two-Scout examples and preserves the incomplete Terror recap.

The Python importer/integration tests verify that the reviewed statistical
snapshot still embeds correctly. No replay import or SQLite change is part
of this patch.
