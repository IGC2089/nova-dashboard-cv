use std::sync::Arc;
use std::time::{Duration, Instant};
use parking_lot::Mutex;
use crate::state::VehicleState;
use zbus::{interface, connection};
use zbus::zvariant::OwnedObjectPath;

const AGENT_PATH: &str = "/nova/agent";
const CAPABILITY:  &str = "DisplayYesNo";
const TIMEOUT_S:   u64  = 30;

struct NovaAgent {
    state: Arc<Mutex<VehicleState>>,
}

#[interface(name = "org.bluez.Agent1")]
impl NovaAgent {
    // Called by BlueZ when a phone wants to pair.
    async fn request_confirmation(
        &self,
        device: OwnedObjectPath,
        passkey: u32,
    ) -> zbus::fdo::Result<()> {
        let device_name = device.to_string();
        log::info!("Pairing request from {device_name} passkey={passkey:06}");

        {
            let mut s = self.state.lock();
            s.bt_pairing_pending  = true;
            s.bt_pairing_device   = device_name;
            s.bt_pairing_passkey  = passkey;
            s.bt_pairing_accepted = None;
        }

        // Poll for user response, timeout after 30s
        let deadline = Instant::now()
            + Duration::from_secs(TIMEOUT_S);

        loop {
            tokio::time::sleep(Duration::from_millis(100)).await;

            let result = {
                let mut s = self.state.lock();
                match s.bt_pairing_accepted {
                    Some(true) => {
                        s.bt_pairing_pending = false;
                        log::info!("Pairing accepted");
                        Some(Ok(()))
                    }
                    Some(false) => {
                        s.bt_pairing_pending = false;
                        log::info!("Pairing rejected");
                        Some(Err(zbus::fdo::Error::AuthFailed("Rejected by user".into())))
                    }
                    None => None,
                }
            };
            if let Some(r) = result { return r; }

            if Instant::now() >= deadline {
                {
                    let mut s = self.state.lock();
                    s.bt_pairing_pending = false;
                }
                log::warn!("Pairing timeout");
                return Err(zbus::fdo::Error::AuthFailed("Timed out".into()));
            }
        }
    }

    async fn cancel(&self) {
        log::info!("Pairing cancelled by BlueZ");
        let mut s = self.state.lock();
        s.bt_pairing_pending  = false;
        s.bt_pairing_accepted = Some(false);
    }

    // Reject PIN and passkey requests — we only support DisplayYesNo
    async fn request_pin_code(&self, _device: OwnedObjectPath) -> zbus::fdo::Result<String> {
        Err(zbus::fdo::Error::NotSupported("Use DisplayYesNo".into()))
    }

    async fn request_passkey(&self, _device: OwnedObjectPath) -> zbus::fdo::Result<u32> {
        Err(zbus::fdo::Error::NotSupported("Use DisplayYesNo".into()))
    }
}

pub fn spawn_bluetooth_thread(state: Arc<Mutex<VehicleState>>) {
    std::thread::Builder::new()
        .name("bluetooth".into())
        .spawn(move || {
            // Create a tokio runtime just for this thread
            let rt = tokio::runtime::Runtime::new().expect("tokio runtime");
            rt.block_on(async {
                if let Err(e) = run_agent(state).await {
                    log::warn!("BT pairing agent error: {e}");
                }
            });
        })
        .expect("BT thread spawn");
}

async fn run_agent(state: Arc<Mutex<VehicleState>>) -> zbus::Result<()> {
    let conn = connection::Builder::system()?
        .serve_at(AGENT_PATH, NovaAgent { state })?
        .build()
        .await?;

    // Register with BlueZ AgentManager
    let manager = zbus::Proxy::new(
        &conn,
        "org.bluez",
        "/org/bluez",
        "org.bluez.AgentManager1",
    )
    .await?;

    let agent_path = zbus::zvariant::ObjectPath::try_from(AGENT_PATH)
        .expect("valid path");

    manager
        .call_method("RegisterAgent", &(&agent_path, CAPABILITY))
        .await?;
    manager
        .call_method("RequestDefaultAgent", &(&agent_path,))
        .await?;

    // Make adapter pairable (ignore failure — adapter may not be hci0)
    if let Ok(adapter) = zbus::Proxy::new(
        &conn,
        "org.bluez",
        "/org/bluez/hci0",
        "org.freedesktop.DBus.Properties",
    )
    .await
    {
        let _ = adapter
            .call_method("Set", &("org.bluez.Adapter1", "Pairable", zbus::zvariant::Value::from(true)))
            .await;
    }

    log::info!("BT pairing agent registered (capability={CAPABILITY})");

    // Run forever (the connection keeps the agent alive)
    std::future::pending::<()>().await;
    Ok(())
}
