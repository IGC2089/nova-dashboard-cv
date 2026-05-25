mod state;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::pixels::Color;
use std::time::{Duration, Instant};

const WIDTH: u32 = 800;
const HEIGHT: u32 = 480;
const FRAME_TIME: Duration = Duration::from_micros(16_667); // ~60 FPS

fn main() {
    env_logger::init();
    let _state = state::new_shared();

    // --- SDL2 setup ---
    let sdl = sdl2::init().expect("SDL2 init failed");
    let video = sdl.video().expect("SDL2 video subsystem failed");

    let window = video
        .window("Nova Dashboard", WIDTH, HEIGHT)
        .borderless()
        .position_centered()
        .build()
        .expect("SDL2 window creation failed");

    let mut canvas = window
        .into_canvas()
        .present_vsync()
        .build()
        .expect("SDL2 canvas creation failed");

    let mut event_pump = sdl.event_pump().expect("SDL2 event pump failed");

    log::info!("Window opened — running at 60 FPS");

    // --- Main loop ---
    'running: loop {
        let frame_start = Instant::now();

        // Handle events
        for event in event_pump.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown { keycode: Some(Keycode::Escape), .. }
                | Event::KeyDown { keycode: Some(Keycode::Q), .. } => {
                    break 'running;
                }
                _ => {}
            }
        }

        // Clear to near-black
        canvas.set_draw_color(Color::RGB(10, 10, 10));
        canvas.clear();
        canvas.present();

        // Cap frame rate
        let elapsed = frame_start.elapsed();
        if elapsed < FRAME_TIME {
            std::thread::sleep(FRAME_TIME - elapsed);
        }
    }

    log::info!("Clean shutdown");
}
