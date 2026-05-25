mod state;
mod renderer;
mod can;
mod gps;
mod bluetooth;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::pixels::PixelFormatEnum;
use sdl2::rect::Rect;
use std::env;
use std::sync::Arc;
use std::time::{Duration, Instant};
use crate::renderer::{Renderer, W, H};
use crate::state::VehicleState;

const FRAME_TIME: Duration = Duration::from_micros(16_667);

fn inject_sim(mut snap: VehicleState, t: f32) -> VehicleState {
    snap.rpm         = 3000.0 + 2500.0 * (t * 0.4).sin();
    snap.speed_kph   = 120.0  + 100.0  * (t * 0.3).sin();
    snap.clt_c       = 85.0   + 15.0   * (t * 0.05).sin().abs();
    snap.fuel_pct    = 0.3    + 0.5    * (t * 0.05).sin().abs();
    snap.afr         = 14.0   + 2.0    * (t * 0.25).sin();
    snap.gps_fix     = true;
    snap.batt_v      = 12.4;
    snap.map_kpa     = 95.0;
    snap.ign_advance = 18.0;
    snap.odo_km      = 12345.0;
    snap.trip_km     = 42.3;
    snap
}

fn handle_tap(x: i32, y: i32, state: &crate::state::SharedState) {
    let mut s = state.lock();
    if !s.bt_pairing_pending { return; }
    let (ax1, ay1, ax2, ay2) = Renderer::PAIRING_ACCEPT_RECT;
    let (rx1, ry1, rx2, ry2) = Renderer::PAIRING_REJECT_RECT;
    if x >= ax1 && x <= ax2 && y >= ay1 && y <= ay2 {
        s.bt_pairing_accepted = Some(true);
        s.bt_pairing_pending  = false;
    } else if x >= rx1 && x <= rx2 && y >= ry1 && y <= ry2 {
        s.bt_pairing_accepted = Some(false);
        s.bt_pairing_pending  = false;
    }
}

fn main() {
    env_logger::init();
    let simulate = env::args().any(|a| a == "--simulate");
    let sim_start = Instant::now();
    if simulate { log::info!("Simulate mode active"); }

    let state = state::new_shared();
    can::spawn_can_thread(Arc::clone(&state));
    gps::spawn_gps_thread(Arc::clone(&state));
    bluetooth::spawn_bluetooth_thread(Arc::clone(&state));

    let sdl   = sdl2::init().expect("SDL2 init");
    let video = sdl.video().expect("SDL2 video");
    let window = video
        .window("Nova Dashboard", W, H)
        .borderless()
        .position_centered()
        .build()
        .expect("window");
    let mut canvas = window.into_canvas().build().expect("canvas");
    let texture_creator = canvas.texture_creator();
    let mut texture = texture_creator
        .create_texture_streaming(PixelFormatEnum::ABGR8888, W, H)
        .expect("texture");
    let mut event_pump = sdl.event_pump().expect("event pump");

    let mut renderer = Renderer::new();
    let mut frame: u64 = 0;

    log::info!("Window opened — render loop started");

    'running: loop {
        let frame_start = Instant::now();

        for event in event_pump.poll_iter() {
            match event {
                Event::Quit { .. }
                | Event::KeyDown { keycode: Some(Keycode::Escape), .. }
                | Event::KeyDown { keycode: Some(Keycode::Q), .. } => break 'running,
                Event::MouseButtonUp { x, y, .. } => handle_tap(x, y, &state),
                _ => {}
            }
        }

        let snap = state.lock().clone();
        let snap = if simulate {
            inject_sim(snap, sim_start.elapsed().as_secs_f32())
        } else {
            snap
        };
        renderer.draw_frame(&snap, frame);
        frame += 1;

        // Blit pixmap → SDL2 texture → screen
        // tiny-skia pixmap is RGBA; ABGR8888 on little-endian Pi = RGBA in memory
        texture
            .update(Rect::new(0, 0, W, H), renderer.pixmap.data(), (W as usize) * 4)
            .expect("texture update");
        canvas.copy(&texture, None, None).expect("canvas copy");
        canvas.present();

        let elapsed = frame_start.elapsed();
        if elapsed < FRAME_TIME {
            std::thread::sleep(FRAME_TIME - elapsed);
        }
    }

    log::info!("Clean shutdown");
}
