use apt::{
    actions::{opcode, ActionStream, DictRefKind, Instruction, PushStringKind},
    append_action_stream, AptFile, ConstFile, Control, Value,
};
use serde_json::Value as Json;
use std::{env, fs, path::PathBuf};
mod club_history_live;

fn member(index: u16) -> Instruction {
    Instruction::DictRef { kind: DictRefKind::ByteGetMember, index }
}
fn property(index: u16) -> Instruction {
    Instruction::DictRef { kind: DictRefKind::PushByte, index }
}
fn literal(s: &str) -> Instruction {
    Instruction::PushString { kind: PushStringKind::Push, value: s.to_owned() }
}
fn inline_member(s: &str) -> Instruction {
    Instruction::PushString { kind: PushStringKind::GetMember, value: s.to_owned() }
}
fn simple(op: u8) -> Instruction { Instruction::Simple(op) }

// All paths below are derived from the original _InitData / _CreateObjectives
// bytecode. The root of the path is register 1 (this).
fn set_section_heading(out: &mut Vec<Instruction>, section: u16, value: &str) {
    out.extend([Instruction::PushRegister(1), member(section), member(106), property(61), literal(value), simple(opcode::SET_MEMBER)]);
}
fn item_path(out: &mut Vec<Instruction>, section: u16, item: &str) {
    let index: u8 = item.strip_prefix("item").expect("item property").parse().expect("item index");
    // Match the original _CreateObjectives sequence: "item" + index, GetMember.
    out.extend([Instruction::PushRegister(1), member(section), property(110),
        Instruction::PushByte(index), simple(opcode::ADD2), simple(opcode::GET_MEMBER)]);
}
fn set_item_text(out: &mut Vec<Instruction>, section: u16, field: u16, value: &str) {
    item_path(out, section, "item0");
    out.extend([member(field), member(106), property(61), literal(value), simple(opcode::SET_MEMBER)]);
}
fn hide_path(out: &mut Vec<Instruction>, section: u16, item: Option<&str>, field: Option<u16>) {
    out.extend([Instruction::PushRegister(1), member(section)]);
    if let Some(name) = item { out.push(inline_member(name)); }
    if let Some(index) = field { out.push(member(index)); }
    out.extend([literal("_visible"), simple(opcode::EA_PUSH_FALSE), simple(opcode::SET_MEMBER)]);
}
fn hide_optional_item(out: &mut Vec<Instruction>, section: u16, name: &str) {
    item_path(out, section, name);
    out.extend([simple(opcode::EA_PUSH_UNDEFINED), simple(opcode::EQUALS2)]);
    let branch = out.len();
    out.push(Instruction::BranchIfTrue { target: 0 });
    hide_path(out, section, Some(name), None);
    let end = out.len();
    out[branch] = Instruction::BranchIfTrue { target: end };
}
fn record_from_json(data: &Json, id: &str, field: &str, count: &str, unit: &str) -> Result<String, Box<dyn std::error::Error>> {
    if data["schema"].as_u64() == Some(2) {
        let key = if field == "top_scorer" { "most_goals" } else { field };
        let obj = &data["clubs"][id]["all_time"][key];
        let name = obj["player_name"].as_str().ok_or("missing player_name")?;
        let n = obj["value"].as_u64().ok_or("missing value")?;
        return Ok(format!("{name} - {n} {unit}"));
    }
    let obj = &data["clubs"][id][field];
    let name = obj["player_name"].as_str().ok_or("missing player_name")?;
    let n = obj[count].as_u64().ok_or("missing count")?;
    if !name.is_ascii() { return Err("APT test strings must be ASCII".into()); }
    Ok(format!("{name} - {n} {unit}"))
}
fn conditional_record(out: &mut Vec<Instruction>, team_id: u16, first: &str, second: &str) {
    out.extend([Instruction::PushRegister(1), member(25), member(57), Instruction::PushWord(team_id), simple(opcode::EQUALS2)]);
    let branch = out.len();
    out.push(Instruction::BranchIfFalse { target: 0 });
    set_item_text(out, 47, 128, first);
    set_item_text(out, 51, 128, second);
    let end = out.len();
    out[branch] = Instruction::BranchIfFalse { target: end };
}
fn patch_init_data(body: &mut ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    let old = body.instructions.len();
    let had_end = matches!(body.instructions.last(), Some(Instruction::End));
    if body.instructions.iter().any(|i| matches!(i, Instruction::BranchAlways{..}|Instruction::BranchIfTrue{..}|Instruction::BranchIfFalse{..})) {
        return Err("_InitData has pre-existing branches; review target shifting".into());
    }
    if had_end { body.instructions.pop(); }
    let out = &mut body.instructions;
    set_section_heading(out, 39, "ALL-TIME TOP SCORER");
    set_section_heading(out, 42, "MOST APPEARANCES");
    hide_path(out, 45, None, None);
    set_item_text(out, 47, 128, "-");
    set_item_text(out, 51, 128, "-");
    set_item_text(out, 47, 130, "");
    set_item_text(out, 51, 130, "");
    hide_path(out, 47, Some("item0"), Some(55));
    hide_path(out, 51, Some("item0"), Some(55));
    for name in ["item1", "item2", "item3", "item4"] {
        hide_optional_item(out, 47, name);
        hide_optional_item(out, 51, name);
    }
    conditional_record(out, 144,
        &record_from_json(data, "144", "top_scorer", "goals", "goals")?,
        &record_from_json(data, "144", "most_appearances", "appearances", "appearances")?);
    conditional_record(out, 1,
        &record_from_json(data, "1", "top_scorer", "goals", "goals")?,
        &record_from_json(data, "1", "most_appearances", "appearances", "appearances")?);
    if had_end { out.push(Instruction::End); }
    Ok(out.len() - old)
}
fn patch_smoke(body: &mut ActionStream) -> Result<usize, Box<dyn std::error::Error>> {
    let old = body.instructions.len();
    // Reuse only opcodes and dictionary entries already present in this APT.
    // Copy the manager name into the permanent primary heading to prove that
    // the relocated _InitData body executes, without adding a new string.
    body.instructions.extend([
        Instruction::PushRegister(1), member(39), member(106), property(61),
        Instruction::PushRegister(1), member(25), member(62), simple(opcode::SET_MEMBER),
    ]);
    Ok(body.instructions.len() - old)
}
fn patch_literal(body: &mut ActionStream) -> Result<usize, Box<dyn std::error::Error>> {
    let old = body.instructions.len();
    set_section_heading(&mut body.instructions, 39, "ALL-TIME TOP SCORER");
    Ok(body.instructions.len() - old)
}
fn patch_one_record(body: &mut ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    let old = body.instructions.len();
    set_section_heading(&mut body.instructions, 39, "ALL-TIME TOP SCORER");
    set_item_text(&mut body.instructions, 47, 128,
        &record_from_json(data, "144", "top_scorer", "goals", "goals")?);
    Ok(body.instructions.len() - old)
}
fn patch_direct_objective(body: &mut ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    // _CreateObjectives(mcObjectives, mcSummary, arrData) reads arrData[i].OBJECTIVE_TITLE
    // when it creates each row. Change the first source value before that loop runs.
    // This diagnostic affects the first row in both groups; no save data is edited.
    let injected = vec![
        Instruction::PushRegister(9), Instruction::PushByte(0), simple(opcode::GET_MEMBER),
        property(127), literal(&record_from_json(data, "144", "top_scorer", "goals", "goals")?),
        simple(opcode::SET_MEMBER),
    ];
    let added = injected.len();
    for instruction in &mut body.instructions {
        match instruction {
            Instruction::BranchAlways { target } | Instruction::BranchIfTrue { target }
            | Instruction::BranchIfFalse { target } => *target += added,
            Instruction::With { .. } | Instruction::Try { .. } =>
                return Err("_CreateObjectives contains an unhandled control span".into()),
            _ => {}
        }
    }
    body.instructions.splice(0..0, injected);
    Ok(added)
}
fn prepend_body(body: &mut ActionStream, injected: Vec<Instruction>) -> Result<usize, Box<dyn std::error::Error>> {
    let added = injected.len();
    for instruction in &mut body.instructions {
        match instruction {
            Instruction::BranchAlways { target } | Instruction::BranchIfTrue { target }
            | Instruction::BranchIfFalse { target } => *target += added,
            Instruction::With { .. } | Instruction::Try { .. } =>
                return Err("method contains an unhandled control span".into()),
            _ => {}
        }
    }
    body.instructions.splice(0..0, injected);
    Ok(added)
}
fn set_first_objective_field(out: &mut Vec<Instruction>, field: u16, value: &str) {
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(0), simple(opcode::GET_MEMBER),
        property(field), literal(value), simple(opcode::SET_MEMBER)]);
}
fn set_first_objective_number(out: &mut Vec<Instruction>, field: u16, value: u8) {
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(0), simple(opcode::GET_MEMBER),
        property(field), Instruction::PushByte(value), simple(opcode::SET_MEMBER)]);
}
fn set_first_objective_symbol(out: &mut Vec<Instruction>, field: u16, symbol: u16) {
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(0), simple(opcode::GET_MEMBER),
        property(field), property(symbol), simple(opcode::SET_MEMBER)]);
}
fn make_synthetic_objective(out: &mut Vec<Instruction>) {
    // Supply our own one-row data object. The original provider's rows are not
    // read; the graph metadata is valid but its movie is hidden after creation.
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(0), Instruction::PushByte(0),
        simple(opcode::INIT_OBJECT), simple(opcode::SET_MEMBER)]);
    for field in [112, 114, 116, 134, 152] { set_first_objective_field(out, field, ""); }
    set_first_objective_symbol(out, 121, 133); // line graph linkage symbol
    for field in [117, 135, 136, 138, 139, 141, 148] { set_first_objective_number(out, field, 0); }
    for field in [140, 142, 150] { set_first_objective_number(out, field, 1); }
    set_first_objective_symbol(out, 154, 155); // string "false"
    set_first_objective_symbol(out, 160, 155);
}
fn set_record_for_team(out: &mut Vec<Instruction>, team_id: u16, value: &str) {
    out.extend([Instruction::PushRegister(1), member(25), member(57), Instruction::PushWord(team_id),
        simple(opcode::EQUALS2), simple(opcode::NOT)]);
    let skip = out.len();
    out.push(Instruction::BranchIfTrue { target: 0 });
    set_first_objective_field(out, 127, value);
    let end = out.len();
    out[skip] = Instruction::BranchIfTrue { target: end };
}
fn patch_records_source(body: &mut ActionStream, data: &Json, hide_graphs: bool, synthetic: bool) -> Result<usize, Box<dyn std::error::Error>> {
    // The native provider still supplies a template objective. The screen replaces
    // its visible title/description before _CreateObjectives reads either field.
    let mut out = Vec::new();
    if synthetic { make_synthetic_objective(&mut out); }
    set_first_objective_field(&mut out, 127, "-");
    set_first_objective_field(&mut out, 129, "");
    out.extend([Instruction::PushRegister(9), property(108), Instruction::PushByte(1), simple(opcode::SET_MEMBER)]);
    out.extend([Instruction::PushRegister(8), Instruction::PushRegister(1), member(47), simple(opcode::STRICT_EQUALS), simple(opcode::NOT)]);
    let secondary = out.len();
    out.push(Instruction::BranchIfTrue { target: 0 });
    set_record_for_team(&mut out, 144, &record_from_json(data, "144", "top_scorer", "goals", "goals")?);
    set_record_for_team(&mut out, 1, &record_from_json(data, "1", "top_scorer", "goals", "goals")?);
    let done = out.len();
    out.push(Instruction::BranchAlways { target: 0 });
    let secondary_target = out.len();
    out[secondary] = Instruction::BranchIfTrue { target: secondary_target };
    set_record_for_team(&mut out, 144, &record_from_json(data, "144", "most_appearances", "appearances", "appearances")?);
    set_record_for_team(&mut out, 1, &record_from_json(data, "1", "most_appearances", "appearances", "appearances")?);
    let end = out.len();
    out[done] = Instruction::BranchAlways { target: end };
    let mut added = 0;
    if hide_graphs {
        // Every graph-type path joins at instruction 349, just before the loop
        // increments i. Register 3 is the newly attached objective movie.
        let at = 349;
        if body.instructions.get(at) != Some(&Instruction::PushRegister(4)) {
            return Err("graph join instruction differs from verified APT".into());
        }
        let hide = [Instruction::PushRegister(3), member(55), literal("_visible"),
            simple(opcode::EA_PUSH_FALSE), simple(opcode::SET_MEMBER)];
        for instruction in &mut body.instructions {
            match instruction {
                Instruction::BranchAlways { target } | Instruction::BranchIfTrue { target }
                | Instruction::BranchIfFalse { target } if *target > at => *target += hide.len(),
                Instruction::With { .. } | Instruction::Try { .. } =>
                    return Err("graph method contains an unhandled control span".into()),
                _ => {}
            }
        }
        body.instructions.splice(at..at, hide);
        added += 5;
    }
    added += prepend_body(body, out)?;
    Ok(added)
}
fn patch_records_frame(body: &mut ActionStream) -> Result<usize, Box<dyn std::error::Error>> {
    let old = body.instructions.len();
    set_section_heading(&mut body.instructions, 39, "ALL-TIME TOP SCORER");
    set_section_heading(&mut body.instructions, 42, "MOST APPEARANCES");
    hide_path(&mut body.instructions, 45, None, None);
    Ok(body.instructions.len() - old)
}
fn history_clubs(data: &Json) -> Result<Vec<(u32, &Json)>, Box<dyn std::error::Error>> {
    if data["schema"].as_u64() != Some(2) || data["competition_scope"].as_str() != Some("all_competitions") {
        return Err("history45 requires schema 2 with all_competitions scope".into());
    }
    let map = data["clubs"].as_object().ok_or("clubs must be an object")?;
    let mut clubs = Vec::new();
    for (key, club) in map {
        let id: u32 = key.parse()?;
        if club["club_id"].as_u64() != Some(id as u64) || club["club_name"].as_str().is_none() {
            return Err(format!("invalid club id/name at {key}").into());
        }
        for (group, keys) in [("all_time", &["most_appearances", "most_goals", "most_assists"][..]),
                              ("single_season", &["most_goals", "most_assists"][..])] {
            for field in keys {
                let record = &club[group][field];
                if !record.is_object() || record.get("player_id").is_none() || record.get("player_name").is_none()
                    || record.get("value").is_none() || record.get("season").is_none() || record.get("source").is_none() {
                    return Err(format!("incomplete record {key}.{group}.{field}").into());
                }
                if !record["player_name"].is_null()
                    && (record["player_name"].as_str().is_none() || record["value"].as_u64().is_none()
                        || !record["source"].is_object()) {
                    return Err(format!("invalid filled record {key}.{group}.{field}").into());
                }
            }
        }
        clubs.push((id, club));
    }
    clubs.sort_by_key(|(id, _)| *id);
    Ok(clubs)
}
fn format_history_value(record: &Json, seasonal: bool) -> Result<String, Box<dyn std::error::Error>> {
    let Some(name) = record["player_name"].as_str() else { return Ok("-".to_string()); };
    // APT literals use Latin-1. Keep the original spelling in the source JSON.
    let name = name.replace('ş', "s").replace('Ş', "S");
    let value = record["value"].as_u64().ok_or("record value missing")?;
    if seasonal {
        let season = record["season"].as_str().ok_or("seasonal record requires season")?;
        Ok(format!("{name} - {value} ({season})"))
    } else {
        Ok(format!("{name} - {value}"))
    }
}
fn array_object(out: &mut Vec<Instruction>, index: u8) {
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(index), simple(opcode::GET_MEMBER)]);
}
fn array_text(out: &mut Vec<Instruction>, index: u8, field: u16, value: &str) {
    array_object(out, index);
    out.extend([property(field), literal(value), simple(opcode::SET_MEMBER)]);
}
fn array_number(out: &mut Vec<Instruction>, index: u8, field: u16, value: u8) {
    array_object(out, index);
    out.extend([property(field), Instruction::PushByte(value), simple(opcode::SET_MEMBER)]);
}
fn array_symbol(out: &mut Vec<Instruction>, index: u8, field: u16, symbol: u16) {
    array_object(out, index);
    out.extend([property(field), property(symbol), simple(opcode::SET_MEMBER)]);
}
fn new_history_row(out: &mut Vec<Instruction>, index: u8) {
    out.extend([Instruction::PushRegister(9), Instruction::PushByte(index), Instruction::PushByte(0),
        simple(opcode::INIT_OBJECT), simple(opcode::SET_MEMBER)]);
    for field in [112, 114, 116, 134, 152] { array_text(out, index, field, ""); }
    array_symbol(out, index, 121, 133); // native line-graph character, hidden after creation
    for field in [117, 135, 136, 138, 139, 141, 148] { array_number(out, index, field, 0); }
    for field in [140, 142, 150] { array_number(out, index, field, 1); }
    array_symbol(out, index, 154, 155); // false
    array_symbol(out, index, 160, 155);
    array_text(out, index, 127, "-");
    array_text(out, index, 129, "-");
}
fn set_array_length(out: &mut Vec<Instruction>, length: u8) {
    out.extend([Instruction::PushRegister(9), property(108), Instruction::PushByte(length), simple(opcode::SET_MEMBER)]);
}
fn if_team(out: &mut Vec<Instruction>, id: u32, emit: impl FnOnce(&mut Vec<Instruction>)) {
    out.extend([Instruction::PushRegister(1), member(25), member(57), Instruction::PushDWord(id),
        simple(opcode::EQUALS2), simple(opcode::NOT)]);
    let skip = out.len();
    out.push(Instruction::BranchIfTrue { target: 0 });
    emit(out);
    out[skip] = Instruction::BranchIfTrue { target: out.len() };
}
fn screen_text(out: &mut Vec<Instruction>, child: u16, value: &str) {
    out.extend([Instruction::PushRegister(1), member(55), member(child), property(61),
        literal(value), simple(opcode::SET_MEMBER)]);
}
fn patch_history45_frame(body: &mut ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    let clubs = history_clubs(data)?;
    let old = body.instructions.len();
    let out = &mut body.instructions;
    set_section_heading(out, 39, "ALL-TIME RECORDS");
    set_section_heading(out, 42, "SINGLE-SEASON RECORDS");
    hide_path(out, 45, None, None); // original manager-objective summary panel
    screen_text(out, 60, "CLUB");
    screen_text(out, 63, "ALL COMPETITIONS");
    for (id, club) in clubs {
        let name = club["club_name"].as_str().ok_or("club_name missing")?.to_uppercase();
        if_team(out, id, |out| screen_text(out, 60, &name));
    }
    Ok(out.len() - old)
}
fn patch_history45_source(body: &mut ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    let clubs = history_clubs(data)?;
    let mut out = Vec::new();
    // Replace the parameter with a local Array. No row or value from the
    // controller's objective data is read or modified by this screen.
    out.extend([Instruction::PushByte(0), property(86), simple(opcode::NEW_OBJECT),
        Instruction::StoreRegister(9), simple(opcode::POP)]);
    for index in 0..2 { new_history_row(&mut out, index); }
    out.extend([Instruction::PushRegister(8), Instruction::PushRegister(1), member(47),
        simple(opcode::STRICT_EQUALS), simple(opcode::NOT)]);
    let secondary = out.len();
    out.push(Instruction::BranchIfTrue { target: 0 });
    new_history_row(&mut out, 2); // third row belongs only to all-time records
    set_array_length(&mut out, 3);
    for (index, label) in [(0, "MOST APPEARANCES"), (1, "MOST GOALS"), (2, "MOST ASSISTS")] {
        array_text(&mut out, index, 127, label);
    }
    for (id, club) in &clubs {
        let values = [format_history_value(&club["all_time"]["most_appearances"], false)?,
                      format_history_value(&club["all_time"]["most_goals"], false)?,
                      format_history_value(&club["all_time"]["most_assists"], false)?];
        if_team(&mut out, *id, |out| {
            for (index, value) in values.iter().enumerate() {
                array_text(out, index as u8, 129, value);
            }
        });
    }
    let done = out.len();
    out.push(Instruction::BranchAlways { target: 0 });
    out[secondary] = Instruction::BranchIfTrue { target: out.len() };
    set_array_length(&mut out, 2);
    for (index, label) in [(0, "MOST GOALS IN A SEASON"), (1, "MOST ASSISTS IN A SEASON")] {
        array_text(&mut out, index, 127, label);
    }
    for (id, club) in &clubs {
        let values = [format_history_value(&club["single_season"]["most_goals"], true)?,
                      format_history_value(&club["single_season"]["most_assists"], true)?];
        if_team(&mut out, *id, |out| {
            for (index, value) in values.iter().enumerate() {
                array_text(out, index as u8, 129, value);
            }
        });
    }
    out[done] = Instruction::BranchAlways { target: out.len() };
    // The original method joins every graph-type branch at instruction 349.
    // Keep the native row title/description, remove objective-only controls,
    // and lay out rows at regular intervals in the existing two columns.
    let at = 349;
    if body.instructions.get(at) != Some(&Instruction::PushRegister(4)) {
        return Err("history45 row join differs from verified APT".into());
    }
    let mut cleanup = Vec::new();
    for field in [55, 124, 166] { // mcData graph, mcPanel, mcCheckBox
        cleanup.extend([Instruction::PushRegister(3), member(field), literal("_visible"),
            simple(opcode::EA_PUSH_FALSE), simple(opcode::SET_MEMBER)]);
    }
    cleanup.extend([Instruction::PushRegister(3), property(123), Instruction::PushRegister(4),
        Instruction::PushByte(64), simple(opcode::MULTIPLY), simple(opcode::SET_MEMBER)]);
    for instruction in &mut body.instructions {
        match instruction {
            Instruction::BranchAlways { target } | Instruction::BranchIfTrue { target }
            | Instruction::BranchIfFalse { target } if *target > at => *target += cleanup.len(),
            Instruction::With { .. } | Instruction::Try { .. } =>
                return Err("history45 source has an unhandled control span".into()),
            _ => {}
        }
    }
    let added_cleanup = cleanup.len();
    body.instructions.splice(at..at, cleanup);
    Ok(added_cleanup + prepend_body(body, out)?)
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let base = PathBuf::from(args.next().ok_or("base path required")?);
    let data_path = PathBuf::from(args.next().ok_or("club_records.json required")?);
    let out_base = PathBuf::from(args.next().ok_or("output base required")?);
    let mode = args.next().unwrap_or_default();
    let data: Json = serde_json::from_slice(&fs::read(&data_path)?)?;
    if !matches!(data["schema"].as_u64(), Some(1) | Some(2)) { return Err("unexpected JSON schema".into()); }
    let apt_in = fs::read(base.with_extension("apt"))?;
    let const_in = fs::read(base.with_extension("const"))?;
    let mut movie = AptFile::read(&apt_in, &const_in)?;
    let mut matches = 0;
    let mut selected_stream: Option<ActionStream> = None;
    for control in &mut movie.movie.frames[0].controls {
        let Control::InitAction { sprite_id, actions } = control else { continue };
        if *sprite_id != 37 { continue; }
        let dictionary = match actions.instructions.first() { Some(Instruction::DefineDictionary(v)) => v, _ => return Err("missing class dictionary".into()) };
        for (index, expected) in [(18, "_InitData"), (24, "ManagerModeSeasonObjectives::_InitData()"), (25, "m_StaticData"), (57, "TEAM_ID"), (43, "PRIMARY_OBJECTIVES"), (49, "SECONDARY_OBJECTIVES")] {
            if dictionary.get(index) != Some(&Value::String(expected.into())) { return Err(format!("dictionary mismatch at {index}: {expected}").into()); }
        }
        for i in 1..actions.instructions.len() {
            let records_mode = matches!(mode.as_str(), "records" | "records_clean" | "records_synthetic" | "history45" | "history12d");
            let is_method = matches!(actions.instructions.get(i-1), Some(Instruction::DictRef { kind: DictRefKind::PushByte, index })
                if (mode == "direct" && *index == 48) || (records_mode && (*index == 18 || *index == 48))
                || (mode != "direct" && !records_mode && *index == 18));
            if !is_method { continue; }
            let wanted_method = match actions.instructions.get(i-1) {
                Some(Instruction::DictRef { index, .. }) => *index, _ => unreachable!(),
            };
            if let Instruction::DefineFunction2 { body, .. } = &mut actions.instructions[i] {
                let expected_trace = if wanted_method == 48 { 107 } else { 24 };
                if body.instructions.first() == Some(&property(expected_trace)) {
                    let added = match mode.as_str() {
                        "smoke" => patch_smoke(body)?,
                        "literal" => patch_literal(body)?,
                        "one" => patch_one_record(body, &data)?,
                        "direct" => patch_direct_objective(body, &data)?,
                        "records" | "records_clean" | "records_synthetic" if wanted_method == 18 => patch_records_frame(body)?,
                        "records" | "records_clean" | "records_synthetic" if wanted_method == 48 =>
                            patch_records_source(body, &data, mode != "records", mode == "records_synthetic")?,
                        "history45" | "history12d" if wanted_method == 18 => {
                            let added = patch_history45_frame(body, &data)?;
                            if mode == "history12d" { club_history_live::init(body); }
                            added
                        },
                        "history45" | "history12d" if wanted_method == 48 =>
                            patch_history45_source(body, &data)?,
                        "" => patch_init_data(body, &data)?,
                        _ => return Err("unknown patch mode".into()),
                    };
                    println!("patched method {wanted_method} in sprite {sprite_id}: {added} added instructions");
                    matches += 1;
                    selected_stream = Some(actions.clone());
                }
            }
        }
    }
    let expected_matches = if matches!(mode.as_str(), "records" | "records_clean" | "records_synthetic" | "history45" | "history12d") { 2 } else { 1 };
    if matches != expected_matches { return Err(format!("expected {expected_matches} target methods, found {matches}").into()); }
    if mode == "history12d" {
        club_history_live::attach_clock(&mut movie)?;
        let (apt, constants) = movie.write(&apt::write::WriteOptions::from_header(&movie.header))?;
        if AptFile::read(&apt, &constants)? != movie { return Err("live club APT roundtrip".into()); }
        fs::write(out_base.with_extension("apt"), apt)?;
        fs::write(out_base.with_extension("const"), constants)?;
        return Ok(());
    }
    let stream = selected_stream.ok_or("patched class stream missing")?;
    let (mut apt_out, new_offset, emitted_consts) = append_action_stream(&apt_in, &stream, movie.header.ptr_size)?;
    let original_consts = ConstFile::read(&const_in, movie.header.ptr_size)?.constants;
    if emitted_consts.len() > original_consts.len() || emitted_consts != original_consts[..emitted_consts.len()] {
        return Err(format!("constant index/order mismatch: emitted {} of {}", emitted_consts.len(), original_consts.len()).into());
    }
    let marker: [u8; 16] = [8,0,0,0,0,0,0,0,37,0,0,0,0,0,0,0];
    let positions: Vec<usize> = apt_in.windows(marker.len()).enumerate()
        .filter_map(|(i, w)| if w == marker { Some(i) } else { None }).collect();
    if positions.len() != 1 { return Err(format!("expected one class control; found {}", positions.len()).into()); }
    let pointer_at = positions[0] + marker.len();
    let old_offset = u64::from_le_bytes(apt_in[pointer_at..pointer_at+8].try_into()?);
    if apt_in[old_offset as usize] != opcode::DEFINE_DICTIONARY { return Err("old class stream marker mismatch".into()); }
    apt_out[pointer_at..pointer_at+8].copy_from_slice(&new_offset.to_le_bytes());
    let const_out = const_in.get(..11702).ok_or("original const entry too small")?;
    if const_in.len() != 11720 { return Err("unexpected original const split length".into()); }
    let reread = AptFile::read(&apt_out, const_out)?;
    if movie != reread { return Err("semantic roundtrip mismatch".into()); }
    fs::write(format!("{}.apt", out_base.display()), &apt_out)?;
    fs::write(format!("{}.const", out_base.display()), const_out)?;
    println!("hybrid parse OK; stream 0x{old_offset:x} -> 0x{new_offset:x}, pointer at 0x{pointer_at:x}, apt {} -> {}, const unchanged {} bytes, emitted constants {}", apt_in.len(), apt_out.len(), const_out.len(), emitted_consts.len());
    Ok(())
}
