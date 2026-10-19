//! Road Trip Adventure launcher for ARM64 Linux handhelds (ArmadaOS on the
//! Retroid Pocket 6, or any aarch64 Linux): sets up ARMSX2, the ARM64
//! PlayStation 2 emulator, for the game with this repository's scripts, keeps
//! it up to date, plays the game and adds it to Steam.

mod app;
mod tasks;

const HELP: &str = "Road Trip Adventure launcher for ARM64

Without options the launcher window opens. It sets up Road Trip Adventure
(PlayStation 2) with ARMSX2 in ~/.local/share/RoadTrip-arm64 from your own
disc image and BIOS, with the scripts of
https://github.com/Ken5998/road-trip-arm64.

  --help     this text
  --version  the launcher's version";

fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("--help" | "-h") => {
            println!("{HELP}");
            return;
        }
        Some("--version" | "-V") => {
            println!("{}", env!("CARGO_PKG_VERSION"));
            return;
        }
        _ => {}
    }

    let options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_title("Road Trip Adventure")
            .with_app_id("roadtrip-launcher")
            .with_inner_size([860.0, 640.0])
            .with_min_inner_size([640.0, 480.0]),
        ..Default::default()
    };
    let result = eframe::run_native(
        "Road Trip Adventure",
        options,
        Box::new(|cc| {
            cc.egui_ctx.set_theme(eframe::egui::Theme::Dark);
            Ok(Box::new(app::LauncherApp::new(cc.egui_ctx.clone())))
        }),
    );
    if let Err(e) = result {
        eprintln!("The launcher window could not open: {e}");
        std::process::exit(1);
    }
}
