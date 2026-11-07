//! Add the scope and observed league candidates to the existing club panel.
use super::{literal, member, property, simple, AptFile, Control, Instruction as I};
use apt::actions::{opcode as o, ActionStream};
use apt::{Character, CharacterSlot, EventAction, Frame, PlaceObject, Sprite};

const CAPACITY: usize = 2048;

fn controller(name: &str) -> Vec<I> {
    vec![I::PushRegister(1), literal(name), simple(o::GET_MEMBER)]
}

fn assign(out: &mut Vec<I>, name: &str, value: Vec<I>) {
    out.extend([I::PushRegister(1), literal(name)]);
    out.extend(value);
    out.push(simple(o::SET_MEMBER));
}

fn branch(out: &mut Vec<I>) -> usize {
    let index = out.len();
    out.push(I::BranchIfFalse { target: 0 });
    index
}

fn close(out: &mut [I], index: usize) {
    out[index] = I::BranchIfFalse { target: out.len() };
}

fn substring(start: u8, end: u8) -> Vec<I> {
    let mut args = vec![I::PushByte(end), I::PushByte(start), I::PushByte(2)];
    args.extend(controller("_dClubPacket"));
    args.extend([literal("substring"), simple(o::CALL_METHOD)]);
    args
}

pub fn init(body: &mut ActionStream) {
    let out = &mut body.instructions;
    let end = matches!(out.last(), Some(I::End));
    if end { out.pop(); }
    assign(out, "_dTicks", vec![I::PushByte(0)]);
    let prefix = "12D_CLUB_WAIT";
    let guard = "END_12D_CLUB";
    let mut tick = Vec::new();
    let mut next = controller("_dTicks");
    next.extend([I::PushByte(1), simple(o::ADD2)]);
    assign(&mut tick, "_dTicks", next);
    tick.extend(controller("_dTicks"));
    tick.extend([I::PushByte(20), simple(o::LESS_THAN2), simple(o::NOT)]);
    let elapsed = branch(&mut tick);
    assign(&mut tick, "_dTicks", vec![I::PushByte(0)]);
    let literal_payload = format!("{prefix}{}{guard}", " ".repeat(CAPACITY-prefix.len()-guard.len()));
    assign(&mut tick, "_dClubPacket", vec![literal(&literal_payload)]);
    tick.extend(controller("_dClubPacket"));
    tick.extend(controller("_dClubPrevious"));
    tick.extend([simple(o::EQUALS2), simple(o::NOT)]);
    let changed = branch(&mut tick);
    assign(&mut tick, "_dClubPrevious", controller("_dClubPacket"));
    super::screen_text(&mut tick, 63, "ALL COMPETITIONS");
    tick.extend(substring(0, 6));
    tick.extend([simple(o::TO_NUMBER), I::PushRegister(1), member(25), member(57), simple(o::TO_NUMBER), simple(o::EQUALS2)]);
    let matches = branch(&mut tick);
    tick.extend([I::PushRegister(1), member(55), member(63), property(61)]);
    tick.extend(substring(7, 39));
    tick.push(simple(o::SET_MEMBER));
    close(&mut tick, matches);
    close(&mut tick, changed);
    close(&mut tick, elapsed);
    assign(out, "_dClubTick", vec![I::DefineFunction2 {
        name: String::new(), params: Vec::new(), register_count: 2, flags: 1,
        body: ActionStream { instructions: tick },
    }]);
    if end { out.push(I::End); }
}

pub fn attach_clock(movie: &mut AptFile) -> Result<(), Box<dyn std::error::Error>> {
    let id = movie.movie.characters.len() as i32;
    movie.movie.characters.push(CharacterSlot::Character(Character::Sprite(Sprite {
        frames: vec![Frame::default()],
    })));
    let CharacterSlot::Character(Character::Sprite(screen)) = &mut movie.movie.characters[36]
    else { return Err("club screen sprite missing".into()); };
    screen.frames[0].controls.push(Control::PlaceObject(PlaceObject {
        depth: 95, character_id: Some(id), name: Some("_clubClock".into()),
        clip_actions: Some(vec![EventAction {
            triggers: 2, key_code: 0, actions: ActionStream { instructions: vec![
                I::PushByte(0), literal("this"), simple(o::GET_VARIABLE), literal("_parent"),
                simple(o::GET_MEMBER), literal("_dClubTick"), simple(o::CALL_METHOD),
                simple(o::POP), I::End,
            ] },
        }]), ..Default::default()
    }));
    Ok(())
}
