use apt::{actions::{opcode, DictRefKind, Instruction, PushStringKind}, append_action_stream,
          AptFile, Character, CharacterSlot, Control, Value};
use serde_json::Value as Json;
use std::{env, fs, path::PathBuf};

fn member(index: u16) -> Instruction {
    Instruction::DictRef { kind: DictRefKind::ByteGetMember, index }
}

fn literal(value: &str) -> Instruction {
    Instruction::PushString { kind: PushStringKind::Push, value: value.into() }
}

fn simple(op:u8)->Instruction {Instruction::Simple(op)}
fn prop(out:&mut Vec<Instruction>,name:&str){out.extend([Instruction::PushRegister(1),literal(name),simple(opcode::GET_MEMBER)]);}
fn assign(out:&mut Vec<Instruction>,name:&str,value:Vec<Instruction>){out.extend([Instruction::PushRegister(1),literal(name)]);out.extend(value);out.push(simple(opcode::SET_MEMBER));}
fn native_list(out:&mut Vec<Instruction>){out.extend([Instruction::PushRegister(1),member(27),Instruction::DictRef{kind:DictRefKind::ByteGetVar,index:1},member(3),member(4),member(5),member(28),simple(opcode::GET_MEMBER)]);}
fn condition(out:&mut Vec<Instruction>)->usize{let at=out.len();out.push(Instruction::BranchIfFalse{target:0});at}
fn end_if(out:&mut [Instruction],at:usize){let end=out.len();out[at]=Instruction::BranchIfFalse{target:end};}
fn dynamic_panel_text(out:&mut Vec<Instruction>,nested:bool,field:u16,value:Vec<Instruction>){panel_path(out,nested,field);out.push(Instruction::DictRef{kind:DictRefKind::PushByte,index:50});out.extend(value);out.push(simple(opcode::SET_MEMBER));}
fn label(out:&mut Vec<Instruction>,line:u8,value:Vec<Instruction>){out.extend([Instruction::PushRegister(1),literal(&format!("_ph12b6_{line}")),simple(opcode::GET_MEMBER),literal("text")]);out.extend(value);out.push(simple(opcode::SET_MEMBER));}
fn index_label(out:&mut Vec<Instruction>){
 let mut v=vec![literal("PLAYER ")];prop(&mut v,"_historyIndex");v.extend([Instruction::PushByte(1),simple(opcode::ADD2),simple(opcode::ADD2),literal(" / "),simple(opcode::ADD2)]);prop(&mut v,"_historyNativeCount");v.extend([simple(opcode::ADD2),literal(" ID "),simple(opcode::ADD2)]);prop(&mut v,"_historyPlayerId");v.push(simple(opcode::ADD2));label(out,0,v);
}
fn dynamic_detail(out:&mut Vec<Instruction>){
 assign(out,"_historyPages",vec![Instruction::PushByte(1)]);
 // Always replace the native portrait request by ID, including players without compiled history.
 prop(out,"_historyPlayerId");out.extend([Instruction::PushByte(0),simple(opcode::GREATER)]);let no_id=condition(out);
 match_info_record(out);out.push(Instruction::DictRef{kind:DictRefKind::PushByte,index:154});prop(out,"_historyPlayerId");out.push(simple(opcode::SET_MEMBER));
 match_info_record(out);out.push(Instruction::DictRef{kind:DictRefKind::PushByte,index:138});prop(out,"_historyName");out.push(simple(opcode::SET_MEMBER));
 out.extend([simple(opcode::EA_PUSH_ZERO),Instruction::PushRegister(1),Instruction::DictRef{kind:DictRefKind::CallMethodPop,index:99}]);end_if(out,no_id);
 panel_path(out,true,81);out.push(member(67));out.push(Instruction::DictRef{kind:DictRefKind::PushByte,index:107});prop(out,"_historyPlayerId");out.extend([Instruction::PushByte(0),simple(opcode::GREATER),simple(opcode::SET_MEMBER)]);
 let mut name=Vec::new();prop(&mut name,"_historyName");dynamic_panel_text(out,false,110,name);
 dynamic_panel_text(out,true,120,vec![Instruction::PushRegister(1),member(35),member(72)]);
 panel_text(out,true,123,"APP    G      A");panel_text(out,true,125,"-       -       -");panel_text(out,true,127,"CS");panel_text(out,true,129,"-");
 panel_text(out,false,169,"CAREER");next_text(out,178,"APP    G      A");next_text(out,180,"-       -       -");next_text(out,182,"CS -");
 out.extend([Instruction::PushRegister(1),member(48),member(60),Instruction::DictRef{kind:DictRefKind::PushByte,index:50},literal("PAGE 1 / 1"),simple(opcode::SET_MEMBER)]);
 index_label(out);label(out,1,vec![literal("NO HISTORY AVAILABLE")]);
 prop(out,"_historyPlayerId");out.extend([Instruction::PushByte(0),simple(opcode::GREATER),simple(opcode::NOT)]);let valid=condition(out);label(out,1,vec![literal("PLAYER IDS UNAVAILABLE")]);end_if(out,valid);
}
fn patch_native_rows(body:&mut apt::actions::ActionStream)->Result<(),Box<dyn std::error::Error>>{
 if body.instructions.len()!=106{return Err("native row initializer changed".into());}
 // 16 history slots regardless of roster size; roster count remains separate.
 insert_handler_code(body,13,vec![Instruction::PushByte(16),Instruction::StoreRegister(3),simple(opcode::POP)])?;
 let mut p=Vec::new();let mut n=Vec::new();native_list(&mut n);n.extend([literal("length"),simple(opcode::GET_MEMBER)]);assign(&mut p,"_historyNativeCount",n);
 prop(&mut p,"_historyIndex");prop(&mut p,"_historyNativeCount");p.extend([simple(opcode::LESS_THAN2),simple(opcode::NOT)]);let in_range=condition(&mut p);assign(&mut p,"_historyIndex",vec![Instruction::PushByte(0)]);assign(&mut p,"_historyPage",vec![Instruction::PushByte(0)]);end_if(&mut p,in_range);
 let mut old=Vec::new();prop(&mut old,"_historyPlayerId");assign(&mut p,"_historyOldId",old);assign(&mut p,"_historyPlayerId",vec![Instruction::PushByte(0)]);assign(&mut p,"_historyName",vec![literal("SQUAD UNAVAILABLE")]);
 prop(&mut p,"_historyNativeCount");p.extend([Instruction::PushByte(0),simple(opcode::GREATER)]);let empty=condition(&mut p);
 let mut name=Vec::new();native_list(&mut name);prop(&mut name,"_historyIndex");name.extend([simple(opcode::GET_MEMBER),member(241)]);assign(&mut p,"_historyName",name);
 let mut id=Vec::new();native_list(&mut id);prop(&mut id,"_historyIndex");id.extend([simple(opcode::GET_MEMBER),literal("PLAYER_ID"),simple(opcode::GET_MEMBER),simple(opcode::TO_NUMBER)]);assign(&mut p,"_historyPlayerId",id);end_if(&mut p,empty);
 prop(&mut p,"_historyOldId");prop(&mut p,"_historyPlayerId");p.extend([simple(opcode::EQUALS2),simple(opcode::NOT)]);let same=condition(&mut p);assign(&mut p,"_historyPage",vec![Instruction::PushByte(0)]);end_if(&mut p,same);
 insert_handler_code(body,0,p)?;Ok(())
}
fn add_dynamic_labels(movie:&mut AptFile)->Result<(),Box<dyn std::error::Error>>{
 let CharacterSlot::Character(Character::Text(template))=&movie.movie.characters[29] else{return Err("text template".into());};let template=template.clone();let mut added=Vec::new();
 for line in 0..2 {let mut t=template.clone();t.bounds=apt::Rect{left:0.0,top:0.0,right:350.0,bottom:18.0};t.font_height=13.0;t.variable.clear();t.multiline=false;t.word_wrap=false;t.initial_text="WAITING".into();let id=movie.movie.characters.len() as i32;movie.movie.characters.push(CharacterSlot::Character(Character::Text(t)));added.push(Control::PlaceObject(apt::PlaceObject{depth:93+line,character_id:Some(id),name:Some(format!("_ph12b6_{line}")),matrix:Some(apt::Matrix{tx:790.0,ty:610.0+line as f32*18.0,..Default::default()}),..Default::default()}));}
 let CharacterSlot::Character(Character::Sprite(s))=&mut movie.movie.characters[56] else{return Err("screen".into());};s.frames[0].controls.extend(added);Ok(())
}

fn replace_headers(body: &mut apt::actions::ActionStream) -> Result<(), Box<dyn std::error::Error>> {
    if body.instructions.iter().any(|x| matches!(x, Instruction::BranchAlways{..} |
        Instruction::BranchIfTrue{..} | Instruction::BranchIfFalse{..} | Instruction::With{..} | Instruction::Try{..})) {
        return Err("InitData control flow changed".into());
    }
    for (source, replacement) in [(37, "PLAYER HISTORY"), (51, "YEAR   APP"),
        (53, "G"), (55, "A"), (57, "CS"), (59, "CLUB / COMPETITION"),
        (61, "PLAYER DETAIL")] {
        let wanted = [Instruction::PushRegister(1), member(35), member(source)];
        let hits: Vec<usize> = body.instructions.windows(3).enumerate()
            .filter_map(|(i, w)| (w == wanted).then_some(i)).collect();
        if hits.len() != 1 { return Err(format!("header {source}: {} sources", hits.len()).into()); }
        body.instructions.splice(hits[0]..hits[0]+3, [literal(replacement)]);
    }
    body.instructions.extend([Instruction::PushRegister(1), literal("_historyIndex"),
        Instruction::PushByte(0), Instruction::Simple(opcode::SET_MEMBER)]);
    body.instructions.extend([Instruction::PushRegister(1), literal("_historyPage"),
        Instruction::PushByte(0), Instruction::Simple(opcode::SET_MEMBER)]);
    body.instructions.extend([Instruction::PushRegister(1), literal("_historyPages"),
        Instruction::PushByte(1), Instruction::Simple(opcode::SET_MEMBER)]);
    Ok(())
}

fn set_row_text(out: &mut Vec<Instruction>, clip: u16, value: &str) {
    out.extend([Instruction::PushRegister(3), member(clip),
        Instruction::DictRef { kind: DictRefKind::PushByte, index: 50 },
        literal(value), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn hide_row_clip(out: &mut Vec<Instruction>, clip: u16) {
    out.extend([Instruction::PushRegister(3), member(clip),
        Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_FALSE), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn panel_path(out: &mut Vec<Instruction>, nested: bool, field: u16) {
    out.extend([Instruction::PushRegister(1), member(44)]);
    if nested { out.push(member(80)); }
    out.push(member(field));
}

fn hide_panel(out: &mut Vec<Instruction>, nested: bool, field: u16) {
    panel_path(out, nested, field);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_FALSE), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn panel_text(out: &mut Vec<Instruction>, nested: bool, field: u16, value: &str) {
    panel_path(out, nested, field);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 50 },
        literal(value), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn next_path(out: &mut Vec<Instruction>, field: u16) {
    out.extend([Instruction::PushRegister(1), member(44), member(173), member(field)]);
}

fn next_text(out: &mut Vec<Instruction>, field: u16, value: &str) {
    next_path(out, field);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 50 },
        literal(value), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn hide_next(out: &mut Vec<Instruction>, field: u16) {
    next_path(out, field);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_FALSE), Instruction::Simple(opcode::SET_MEMBER)]);
}

fn patch_detail_panel(body: &mut apt::actions::ActionStream) -> Result<(), Box<dyn std::error::Error>> {
    if body.instructions.len() != 681 || body.instructions.get(649) != Some(&Instruction::BranchAlways { target: 681 }) {
        return Err("_InitMatchInfo structure changed".into());
    }
    let out = &mut body.instructions;
    // All original paths converge at instruction 681; appended actions remove
    // match context while keeping the built-in portrait loader.
    for field in [113, 172, 47] { hide_panel(out, false, field); }
    for field in [43, 83, 119, 122, 125, 131, 134, 139,
        142, 144, 146, 148, 150, 152, 164, 87, 89, 91] {
        hide_panel(out, true, field);
    }
    panel_text(out, false, 110, "PLAYER");
    panel_text(out, true, 120, "CLUB");
    panel_text(out, true, 123, "APP    G      A");
    panel_text(out, true, 125, "-       -       -");
    panel_text(out, true, 127, "CS");
    panel_text(out, true, 129, "-");
    panel_text(out, false, 169, "CAREER");
    next_text(out, 178, "APP    G      A");
    next_text(out, 180, "-       -       -");
    next_text(out, 182, "CS -");
    // txtPrevAwayName (125) is one of the two competition labels, so show it.
    panel_path(out, true, 125);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_TRUE), Instruction::Simple(opcode::SET_MEMBER)]);
    panel_path(out, false, 80);
    out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_TRUE), Instruction::Simple(opcode::SET_MEMBER)]);
    for field in [120, 123, 125, 127, 129] {
        panel_path(out, true, field);
        out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
            Instruction::Simple(opcode::EA_PUSH_TRUE), Instruction::Simple(opcode::SET_MEMBER)]);
    }
    for field in [169, 173] {
        panel_path(out, false, field);
        out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
            Instruction::Simple(opcode::EA_PUSH_TRUE), Instruction::Simple(opcode::SET_MEMBER)]);
    }
    for field in [175, 176, 184, 186] { hide_next(out, field); }
    for field in [178, 180, 182] {
        next_path(out, field);
        out.extend([Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
            Instruction::Simple(opcode::EA_PUSH_TRUE), Instruction::Simple(opcode::SET_MEMBER)]);
    }
    Ok(())
}

fn count(record: Option<&Json>, field: &str) -> String {
    record.and_then(|r| r[field].as_u64()).map(|v| v.to_string()).unwrap_or_else(|| "-".into())
}

fn match_info_record(out: &mut Vec<Instruction>) {
    out.extend([Instruction::PushRegister(1), member(27),
        Instruction::DictRef { kind: DictRefKind::ByteGetVar, index: 1 },
        member(3), member(4), member(5), member(109),
        Instruction::Simple(opcode::GET_MEMBER), Instruction::Simple(opcode::EA_PUSH_ZERO),
        Instruction::Simple(opcode::GET_MEMBER)]);
}

fn total_line(totals: &Json) -> String {
    let val = |key: &str| totals[key].as_u64().map(|v| v.to_string()).unwrap_or_else(|| "-".into());
    format!("{:<8}{:<8}{}", val("appearances"), val("goals"), val("assists"))
}

fn total_pi(totals: &Json, _goalkeeper: bool) -> String {
    totals["clean_sheets"].as_u64().map(|v| v.to_string()).unwrap_or_else(|| "-".into())
}

fn set_portrait(out:&mut Vec<Instruction>,player:&Json,_player_id:u32,_name:&str,page:usize,pages:usize){
 out.extend([Instruction::PushRegister(1),member(48),member(60),Instruction::DictRef{kind:DictRefKind::PushByte,index:50},literal(&format!("PAGE {} / {}",page+1,pages)),simple(opcode::SET_MEMBER)]);
 panel_text(out,true,125,&total_line(&player["current_club_totals"]));panel_text(out,true,129,&total_pi(&player["current_club_totals"],false));next_text(out,180,&total_line(&player["career_totals"]));next_text(out,182,&format!("CS {}",total_pi(&player["career_totals"],false)));
 label(out,1,vec![literal(player["history_source_note"].as_str().unwrap_or("COMPILED HISTORY"))]);
}

fn players_for_ui(data:&Json)->Result<Vec<&Json>,Box<dyn std::error::Error>>{
 let players=data["players"].as_object().ok_or("players object")?;let mut list:Vec<_>=players.values().collect();list.sort_by_key(|p|p["player_id"].as_u64().unwrap_or(0));if list.is_empty() && data["runtime_only"]!=true{return Err("empty history library".into());}Ok(list)
}

fn row_visible(out: &mut Vec<Instruction>, visible: bool) {
    out.extend([Instruction::PushRegister(3),
        Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(if visible { opcode::EA_PUSH_TRUE } else { opcode::EA_PUSH_FALSE }),
        Instruction::Simple(opcode::SET_MEMBER)]);
}

fn render_history_row(out: &mut Vec<Instruction>, season: &str, apps: &str, goals: &str,
                      assists: &str, clean: &str, club_competition: &str) {
    row_visible(out, true);
    for (clip, value) in [(230, apps), (232, season), (234, goals), (236, assists),
                          (238, clean), (240, club_competition)] {
        set_row_text(out, clip, value);
    }
}

fn patch_rows(body: &mut apt::actions::ActionStream, data: &Json) -> Result<usize, Box<dyn std::error::Error>> {
    const PAGE_SIZE: usize = 16;
    if body.instructions.len() != 234 || body.instructions.get(17) != Some(&Instruction::StoreRegister(4))
        || body.instructions.get(100) != Some(&member(241)) { return Err("UpdateRowPlayers structure changed".into()); }
    let players = players_for_ui(data)?;
    body.instructions.clear();
    let mut extra = Vec::new();
    set_row_text(&mut extra, 230, "");
    // Native ranking used to assign these colors; the history renderer now owns all six cells.
    for clip in [230,232,234,236,238,240] {
        extra.extend([Instruction::PushRegister(3),member(clip),
            Instruction::DictRef{kind:DictRefKind::PushByte,index:62},
            Instruction::DictRef{kind:DictRefKind::ByteGetVar,index:1},
            member(12),member(63),member(64),simple(opcode::SET_MEMBER)]);
    }
    for clip in [220, 254, 255] { hide_row_clip(&mut extra, clip); }
    extra.extend([Instruction::PushRegister(3), member(238),
        Instruction::DictRef { kind: DictRefKind::PushByte, index: 62 },
        Instruction::DictRef { kind: DictRefKind::ByteGetVar, index: 1 },
        member(12), member(63), member(64), Instruction::Simple(opcode::SET_MEMBER)]);
    row_visible(&mut extra, false);
    // Original ranking scroll bar has no meaning for a player's season rows.
    extra.extend([Instruction::PushRegister(1), member(48), member(213),
        Instruction::DictRef { kind: DictRefKind::PushByte, index: 107 },
        Instruction::Simple(opcode::EA_PUSH_FALSE), Instruction::Simple(opcode::SET_MEMBER)]);
    extra.extend([Instruction::PushRegister(7),Instruction::PushByte(0),simple(opcode::EQUALS2)]);let not_first=condition(&mut extra);
    render_history_row(&mut extra,"","","","","","NO HISTORY AVAILABLE");dynamic_detail(&mut extra);end_if(&mut extra,not_first);
    for player in &players {
        if player["records"].as_array().ok_or("records")?.is_empty(){continue;}

        let name = player["display_name"].as_str().ok_or("display name")?;
        let player_id = u32::try_from(player["player_id"].as_u64().ok_or("player id")?)?;
        prop(&mut extra,"_historyPlayerId");
        extra.extend([Instruction::PushDWord(player_id),simple(opcode::EQUALS2)]);
        extra.extend([Instruction::PushRegister(1),member(35),member(68),simple(opcode::TO_NUMBER),Instruction::PushDWord(player["context_team_id"].as_u64().ok_or("history context club")? as u32),simple(opcode::EQUALS2),simple(opcode::AND)]);
        let skip_player = extra.len();
        extra.push(Instruction::BranchIfFalse { target: 0 });
        let records = player["records"].as_array().ok_or("records")?;
        let goalkeeper = player["is_goalkeeper"].as_bool().unwrap_or(false);
        if records.len() > 512 { return Err(format!("{name} exceeds 512 compiled rows").into()); }
        let pages = records.len().max(1).div_ceil(PAGE_SIZE);
        extra.extend([Instruction::PushRegister(1), literal("_historyPages"),
            Instruction::PushByte(pages as u8), Instruction::Simple(opcode::SET_MEMBER)]);
        for page in 0..pages {
            history_page(&mut extra);
            extra.extend([Instruction::PushByte(page as u8), Instruction::Simple(opcode::EQUALS2)]);
            let skip_page = extra.len();
            extra.push(Instruction::BranchIfFalse { target: 0 });
            let visible_count = (records.len().saturating_sub(page * PAGE_SIZE)).min(PAGE_SIZE).max(1);
            for row_index in 0..visible_count {
            extra.extend([Instruction::PushRegister(7), Instruction::PushByte(row_index as u8),
                Instruction::Simple(opcode::EQUALS2)]);
            let skip_row = extra.len();
            extra.push(Instruction::BranchIfFalse { target: 0 });
            if let Some(record) = records.get(page * PAGE_SIZE + row_index) {
                let season = record["season_label"].as_str().ok_or("season label")?;
                let short = season.get(2..).ok_or("season label format")?;
                let competition = record["competition_display"].as_str().ok_or("competition")?;
                let club = record["club_name"].as_str().ok_or("club")?;
                let club_competition = format!("{club} / {competition}");
                let clean = if goalkeeper { count(Some(record), "clean_sheets") } else { "-".into() };
                render_history_row(&mut extra, short,
                    &count(Some(record), "appearances"), &count(Some(record), "goals"),
                    &count(Some(record), "assists"), &clean, &club_competition);
            }
            if row_index == 0 { set_portrait(&mut extra, player, player_id, name, page, pages); }
            extra[skip_row] = Instruction::BranchIfFalse { target: extra.len() };
            }
            extra[skip_page] = Instruction::BranchIfFalse { target: extra.len() };
        }
        extra[skip_player] = Instruction::BranchIfFalse { target: extra.len() };
    }
    let offset = body.instructions.len();
    for ins in &mut extra {
        if let Instruction::BranchIfFalse { target } = ins { *target += offset; }
    }
    body.instructions.extend(extra);
    Ok(players.len())
}

fn history_index(out: &mut Vec<Instruction>) {
    out.extend([Instruction::PushRegister(1), literal("_historyIndex"),
        Instruction::Simple(opcode::GET_MEMBER)]);
}

fn history_page(out: &mut Vec<Instruction>) {
    out.extend([Instruction::PushRegister(1), literal("_historyPage"),
        Instruction::Simple(opcode::GET_MEMBER)]);
}

fn move_selector(up: bool, _player_count: usize) -> Vec<Instruction> {
    let mut out = Vec::new();
    prop(&mut out,"_historyNativeCount");out.extend([Instruction::PushByte(0),simple(opcode::GREATER)]);let empty=condition(&mut out);
    if up {
        out.push(Instruction::PushByte(0));
        history_index(&mut out);
    } else {
        history_index(&mut out);
        prop(&mut out,"_historyNativeCount");out.extend([Instruction::PushByte(1),simple(opcode::SUBTRACT)]);
    }
    out.push(Instruction::Simple(opcode::LESS_THAN2));
    let skip = out.len();
    out.push(Instruction::BranchIfFalse { target: 0 });
    out.extend([Instruction::PushRegister(1), literal("_historyIndex")]);
    history_index(&mut out);
    out.extend([Instruction::PushByte(1), Instruction::Simple(if up { opcode::SUBTRACT } else { opcode::ADD2 }),
        Instruction::Simple(opcode::SET_MEMBER)]);
    let end_normal = out.len();
    out.push(Instruction::BranchAlways { target: 0 });
    out[skip] = Instruction::BranchIfFalse { target: out.len() };
    out.extend([Instruction::PushRegister(1), literal("_historyIndex")]);
    if up {
        prop(&mut out,"_historyNativeCount");out.extend([Instruction::PushByte(1),simple(opcode::SUBTRACT)]);
    } else {
        out.push(Instruction::PushByte(0));
    }
    out.push(Instruction::Simple(opcode::SET_MEMBER));
    out[end_normal] = Instruction::BranchAlways { target: out.len() };
    out.extend([Instruction::PushRegister(1), literal("_historyPage"),
        Instruction::PushByte(0), Instruction::Simple(opcode::SET_MEMBER)]);
    // Rebuild the native row control to invoke UpdateRowPlayers for the newly
    // selected player's season rows. The old ranking data remains untouched.
    out.extend([Instruction::Simple(opcode::EA_PUSH_ZERO), Instruction::PushRegister(1),
        Instruction::DictRef { kind: DictRefKind::CallMethodPop, index: 33 }]);
    end_if(&mut out,empty);
    out.push(Instruction::BranchAlways { target: usize::MAX });
    out
}

fn move_page(previous: bool) -> Vec<Instruction> {
    let mut out = Vec::new();
    if previous {
        out.push(Instruction::PushByte(0));
        history_page(&mut out);
    } else {
        history_page(&mut out);
        out.extend([Instruction::PushRegister(1), literal("_historyPages"),
            Instruction::Simple(opcode::GET_MEMBER), Instruction::PushByte(1),
            Instruction::Simple(opcode::SUBTRACT)]);
    }
    out.push(Instruction::Simple(opcode::LESS_THAN2));
    let wrap = out.len();
    out.push(Instruction::BranchIfFalse { target: 0 });
    out.extend([Instruction::PushRegister(1), literal("_historyPage")]);
    history_page(&mut out);
    out.extend([Instruction::PushByte(1), Instruction::Simple(if previous { opcode::SUBTRACT } else { opcode::ADD2 }),
        Instruction::Simple(opcode::SET_MEMBER)]);
    let end_normal = out.len();
    out.push(Instruction::BranchAlways { target: 0 });
    out[wrap] = Instruction::BranchIfFalse { target: out.len() };
    out.extend([Instruction::PushRegister(1), literal("_historyPage")]);
    if previous {
        out.extend([Instruction::PushRegister(1), literal("_historyPages"),
            Instruction::Simple(opcode::GET_MEMBER), Instruction::PushByte(1),
            Instruction::Simple(opcode::SUBTRACT)]);
    } else { out.push(Instruction::PushByte(0)); }
    out.push(Instruction::Simple(opcode::SET_MEMBER));
    out[end_normal] = Instruction::BranchAlways { target: out.len() };
    out.extend([Instruction::Simple(opcode::EA_PUSH_ZERO), Instruction::PushRegister(1),
        Instruction::DictRef { kind: DictRefKind::CallMethodPop, index: 33 }]);
    out.push(Instruction::BranchAlways { target: usize::MAX });
    out
}

fn insert_handler_code(body: &mut apt::actions::ActionStream, at: usize, mut code: Vec<Instruction>) -> Result<(), Box<dyn std::error::Error>> {
    let count = code.len();
    for ins in &mut code {
        match ins {
            Instruction::BranchAlways { target } if *target == usize::MAX => *target = body.instructions.len() + count,
            Instruction::BranchIfFalse { target } | Instruction::BranchAlways { target } => *target += at,
            _ => {}
        }
    }
    for ins in &mut body.instructions {
        match ins {
            Instruction::BranchAlways { target } | Instruction::BranchIfTrue { target } |
            Instruction::BranchIfFalse { target } if *target > at => *target += count,
            Instruction::With { .. } | Instruction::Try { .. } => return Err("event handler span".into()),
            _ => {}
        }
    }
    body.instructions.splice(at..at, code);
    Ok(())
}

fn patch_event_handler(body: &mut apt::actions::ActionStream, player_count: usize) -> Result<(), Box<dyn std::error::Error>> {
    if body.instructions.len() != 161 || body.instructions.get(25) != Some(&Instruction::BranchIfTrue { target: 80 })
        || body.instructions.get(34) != Some(&Instruction::BranchIfTrue { target: 99 })
        || body.instructions.get(43) != Some(&Instruction::BranchIfTrue { target: 118 })
        || body.instructions.get(52) != Some(&Instruction::BranchIfTrue { target: 139 }) {
        return Err("LocalEventHandler navigation changed".into());
    }
    // UI_UP/UI_DOWN change pages; R1/L1 change players. BACK is untouched.
    insert_handler_code(body, 139, move_selector(true, player_count))?;
    insert_handler_code(body, 118, move_selector(false, player_count))?;
    insert_handler_code(body, 99, move_page(false))?;
    insert_handler_code(body, 80, move_page(true))?;
    Ok(())
}

fn align_row_and_headers(movie: &mut AptFile) -> Result<(), Box<dyn std::error::Error>> {
    for (id, placements) in [
        (11usize, [("txtPrevRank", 31.0), ("txtRank", 95.0),
                   ("txtPosition", 150.0), ("txtOverall", 205.0),
                   ("txtForm", 260.0), ("txtPlayer", 310.0)].as_slice()),
        (26usize, [("txtRankHeader", 31.0), ("txtPosHeader", 150.0),
                   ("txtOvrHeader", 205.0), ("txtFormHeader", 260.0),
                   ("txtPlayerHeader", 310.0)].as_slice()),
    ] {
        let CharacterSlot::Character(Character::Sprite(sprite)) = &mut movie.movie.characters[id] else {
            return Err(format!("sprite {id} missing").into());
        };
        for (name, x) in placements {
            let matches: Vec<_> = sprite.frames[0].controls.iter_mut().filter_map(|control| {
                let Control::PlaceObject(place) = control else { return None };
                (place.name.as_deref() == Some(*name)).then_some(place)
            }).collect();
            if matches.len() != 1 { return Err(format!("{name} placement count {}", matches.len()).into()); }
            let matrix = matches.into_iter().next().unwrap().matrix.as_mut().ok_or("missing matrix")?;
            matrix.tx = *x;
        }
    }
    for (id, placements) in [
        (41usize, [("mcPlayerHead", 0.0, 15.0), ("txtPrevDate", 31.5, 180.0),
                   ("txtPrevHomeName", 31.5, 210.0), ("txtPrevAwayName", 31.5, 238.0),
                   ("txtPrevHomeScore", 308.5, 210.0), ("txtPrevAwayScore", 308.5, 238.0)].as_slice()),
        (53usize, [("txtNextHeader", 6.5, 313.0), ("mcUpcomingMatchData", 8.0, 341.0)].as_slice()),
    ] {
        let CharacterSlot::Character(Character::Sprite(sprite)) = &mut movie.movie.characters[id] else {
            return Err(format!("panel sprite {id} missing").into());
        };
        for (name, x, y) in placements {
            let matches: Vec<_> = sprite.frames[0].controls.iter_mut().filter_map(|control| {
                let Control::PlaceObject(place) = control else { return None };
                (place.name.as_deref() == Some(*name)).then_some(place)
            }).collect();
            if matches.len() != 1 { return Err(format!("{name} placement count {}", matches.len()).into()); }
            let matrix = matches.into_iter().next().unwrap().matrix.as_mut().ok_or("missing panel matrix")?;
            matrix.tx = *x;
            matrix.ty = *y;
        }
    }
    let CharacterSlot::Character(Character::Text(title)) = &mut movie.movie.characters[33] else {
        return Err("current club title character missing".into());
    };
    title.bounds.right = 270.0;
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let base = PathBuf::from(env::args().nth(1).ok_or("base path")?);
    let output = PathBuf::from(env::args().nth(2).ok_or("output base")?);
    let data_path = PathBuf::from(env::args().nth(3).ok_or("player_history.json path")?);
    let data: Json = serde_json::from_slice(&fs::read(data_path)?)?;
    let player_count = players_for_ui(&data)?.len();
    let apt_in = fs::read(base.with_extension("apt"))?;
    let const_in = fs::read(base.with_extension("const"))?;
    let mut movie = AptFile::read(&apt_in, &const_in)?;
    let mut selected = None;
    let mut sprite = 0;
    let mut patched = 0;
    let mut included = 0;
    for control in &mut movie.movie.frames[0].controls {
        let Control::InitAction { sprite_id, actions } = control else { continue };
        let dictionary = match actions.instructions.first() {
            Some(Instruction::DefineDictionary(values)) => values, _ => continue
        };
        if dictionary.get(34) != Some(&Value::String("SquadRanking::InitData()".into())) { continue; }
        if dictionary.get(37) != Some(&Value::String("SCREEN_TITLE".into()))
            || dictionary.get(211) != Some(&Value::String("UpdateRowPlayers".into()))
            || dictionary.get(241) != Some(&Value::String("DATA_PLAYER".into()))
            || dictionary.get(266) != Some(&Value::String("LocalEventHandler".into())) {
            return Err("dictionary mismatch".into());
        }
        for i in 1..actions.instructions.len() {
            let method = match actions.instructions.get(i-1) {
                Some(Instruction::DictRef { kind: DictRefKind::PushByte | DictRefKind::PushWord, index }) => *index,
                _ => continue,
            };
            let Instruction::DefineFunction2 { body, .. } = &mut actions.instructions[i] else { continue };
            if method == 17 && body.instructions.first() == Some(&Instruction::DictRef { kind: DictRefKind::PushByte, index: 34 }) {
                replace_headers(body)?;
                patched += 1;
            } else if method == 33 {
                patch_native_rows(body)?;
                patched += 1;
            } else if method == 211 && body.instructions.first() == Some(&Instruction::DictRef { kind: DictRefKind::PushByte, index: 219 }) {
                included = patch_rows(body, &data)?;
                patched += 1;
            } else if method == 99 && body.instructions.first() == Some(&Instruction::DictRef { kind: DictRefKind::PushByte, index: 108 }) {
                patch_detail_panel(body)?;
                patched += 1;
            } else if method == 266 && body.instructions.first() == Some(&Instruction::DictRef { kind: DictRefKind::PushWord, index: 271 }) {
                patch_event_handler(body, player_count)?;
                patched += 1;
            }
        }
        if patched == 5 {
            if selected.is_some() { return Err("multiple SquadRanking streams".into()); }
            selected = Some(actions.clone());
            sprite = *sprite_id;
        }
    }
    if patched != 5 || (included < 5 && data["runtime_only"]!=true) { return Err(format!("patched={patched}, players={included}").into()); }
    let stream = selected.ok_or("SquadRanking InitData not found")?;
    let (mut apt_out, new_offset, constants) = append_action_stream(&apt_in, &stream, movie.header.ptr_size)?;
    let original = apt::ConstFile::read(&const_in, movie.header.ptr_size)?.constants;
    if constants.len() > original.len() || constants != original[..constants.len()] {
        return Err("constant mismatch".into());
    }
    let mut marker = vec![8,0,0,0,0,0,0,0];
    if sprite < 0 { return Err("negative sprite id".into()); }
    marker.extend_from_slice(&(sprite as u64).to_le_bytes());
    let positions: Vec<usize> = apt_in.windows(marker.len()).enumerate()
        .filter_map(|(i, w)| (w == marker).then_some(i)).collect();
    if positions.len() != 1 { return Err(format!("class control count {}", positions.len()).into()); }
    let pointer = positions[0] + marker.len();
    let old_offset = u64::from_le_bytes(apt_in[pointer..pointer+8].try_into()?);
    if apt_in[old_offset as usize] != opcode::DEFINE_DICTIONARY { return Err("old stream marker".into()); }
    apt_out[pointer..pointer+8].copy_from_slice(&new_offset.to_le_bytes());
    if AptFile::read(&apt_out, &const_in)? != movie { return Err("semantic roundtrip mismatch".into()); }
    let mut aligned = AptFile::read(&apt_out, &const_in)?;
    align_row_and_headers(&mut aligned)?;
    add_dynamic_labels(&mut aligned)?;
    let (apt_out, const_out) = aligned.write(&apt::write::WriteOptions::from_header(&aligned.header))?;
    if AptFile::read(&apt_out, &const_out)? != aligned { return Err("aligned roundtrip mismatch".into()); }
    fs::write(output.with_extension("apt"), apt_out)?;
    fs::write(output.with_extension("const"), const_out)?;
    println!("history rows for {included} players: sprite {sprite}, old {old_offset:#x}, new {new_offset:#x}");
    Ok(())
}
