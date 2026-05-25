mod state;

fn main() {
    let _state = state::new_shared();
    println!("nova-dashboard starting — state OK");
}
