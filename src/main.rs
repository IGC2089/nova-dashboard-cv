mod state;
mod renderer;

use sdl2::event::Event;
use sdl2::keyboard::Keycode;
use sdl2::pixels::PixelFormatEnum;
use sdl2::rect::Rect;
use std::time::{Duration, Instant};
use crate::renderer::{Renderer, W, H};

const FRAME_TIME: Duration = Duration::from_micros(16_667);

fn main() {
    env_logger::init();
    let state = state::new_shared();

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
                _ => {}
            }
        }

        let snap = state.lock().clone();
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
