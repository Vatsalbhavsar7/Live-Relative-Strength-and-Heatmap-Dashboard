# Multi-Device Server & Client Setup Guide
## Angel One Live Relative Strength & Heatmap Dashboard (Project 06)

This guide explains how to run Project 06 across **two separate devices**:
- **Server (Linux PC)**: Runs `run_collector.py` 24/7 headless. Automatically starts collection at 09:14:00 AM on trading days, streams SmartStream 2.0 ticks, aggregates 1-minute OHLC bars into MySQL, flushes & closes at 15:30:30 PM, and sleeps on weekends & holidays without hitting API rate limits.
- **Client (Windows Laptop)**: Runs `run_dashboard.py` (PySide6 GUI) anytime during or after market hours to visualize live tick curves, multi-day historical charts, momentum surge radar, and the market-cap weighted heatmap.

---

## 1. Angel One Account Credentials & Static IP Setup on Linux PC

### A. Where to Put Angel One Credentials
On your Linux PC, create or copy `USER_CREDENTIALS.json` in either:
- The repository root: `AlgoTradingPythonProjects/USER_CREDENTIALS.json` OR
- Inside the project folder: `projects/06_live_relative_strength_and_heatmap_dashboard/USER_CREDENTIALS.json`

File contents:
```json
[
  {
    "broker_name": "angelone",
    "is_active": true,
    "credentials": {
      "api_key": "YOUR_ANGELONE_API_KEY",
      "client_code": "YOUR_CLIENT_CODE",
      "password": "YOUR_PASSWORD_OR_PIN",
      "totp_secret": "YOUR_TOTP_QR_SECRET_KEY"
    }
  }
]
```
> [!NOTE]
> `USER_CREDENTIALS.json` is strictly ignored by `.gitignore` and will never be pushed to GitHub.

### B. Understanding the Static IP Rule
In Angel One SmartAPI, the "Static IP" rule validates the **Public Outbound IP Address** (WAN IP) of your internet connection when authenticating.
- **Office Wi-Fi (Laptop) & Office LAN (Linux PC)**:
  Both your laptop and Linux PC connect to the same office router/switch. All devices on the office network share the **exact same external Public Static IP**.
- **Result**:
  Because your Linux PC exits through the exact same office static IP registered in your Angel One SmartAPI portal, **no changes are needed in the Angel One dashboard**. Your Linux PC will authenticate seamlessly!

---

## 2. Server Host IP Discovery

When you run `run_collector.py` (or `python run_collector.py --status`) on your Linux PC, it **automatically detects and prints the host IP address**:

```text
==============================================================================
  ANGEL ONE - RELATIVE STRENGTH COLLECTOR (SERVICE 1) STATUS
==============================================================================
  Current Local Time : 2026-11-27 10:44:17 (Friday)
  Market Status      : OPEN (Market Open (Regular Trading Session))
  Maintenance Mode   : OFF
  Data Retention     : 5 Days
------------------------------------------------------------------------------
  HOST IP ADDRESSES FOR CLIENT DASHBOARD (connection_config.json):
    • Office LAN IP    : 192.168.x.x  (Use when Laptop & PC are in same office)
    • Tailscale Mesh IP: 100.85.x.y   (Use for encrypted connection anywhere)
------------------------------------------------------------------------------
  ANGEL ONE ACCOUNT & STATIC IP STATUS:
    • Client Code / ID : B59777747 (Active in USER_CREDENTIALS.json)
    • Static IP Note   : PC (LAN) and Laptop (Wi-Fi) share same Office Router
==============================================================================
```

Simply copy the **Office LAN IP** (or **Tailscale Mesh IP**) into your laptop's configuration!

---

## 3. Network Connectivity: Office LAN vs Tailscale

You have two easy ways to connect your Windows Laptop to your Linux PC:

### Option A: Direct Office LAN (Fastest & Simplest)
If your Linux PC and Windows Laptop are in the same office:
1. Note the **Office LAN IP** printed by `run_collector.py` (e.g. `192.168.1.50`).
2. Put `"host": "192.168.1.50"` in your laptop's `connection_config.json`.
3. No VPN or third-party software needed!

### Option B: Tailscale (Works Anywhere in the World)
If your office Wi-Fi and office LAN are isolated by a firewall/VLAN, or if you take your laptop home:
1. **Windows Laptop**: Install Tailscale from [tailscale.com/download](https://tailscale.com/download).
2. **Linux PC**:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   tailscale up
   ```
3. Sign into both devices with the same account.
4. Note your Linux PC's Tailscale IP (e.g. `100.85.120.45`).

---

## 4. Zero-Sudo Remote Access via Python TCP Bridge (Port 3307)

You **do not need `sudo` privileges** or system administrator access on the Linux PC!

`run_collector.py` contains a built-in user-space TCP forwarder (`tcp_bridge.py`):
- When you launch `python3 run_collector.py` on Linux, it automatically starts listening on `0.0.0.0:3307`.
- Any query received on port 3307 is forwarded locally to MySQL (`127.0.0.1:3306`).
- **No changes needed to `/etc/mysql/mysql.conf.d/mysqld.cnf`!**
- **No `sudo systemctl restart mysql` needed!**
- **No firewall adjustments needed** if connecting over LAN or Tailscale!

---

## 5. Configure Windows Laptop Dashboard (Client)

To connect your Windows Laptop dashboard to the Linux PC, choose either method:

### Method A: Quick Edit in `config.py` (Easiest)
In `config.py` on your Windows Laptop, change only two lines:
```python
DB_HOST = "192.168.2.130"   # <-- Replace with your Linux PC's LAN IP address
DB_PORT = 3307               # <-- Port 3307 routes to MySQL via Python TCP Bridge
```

### Method B: Using `connection_config.json`
Create or copy `connection_config.json` in the project folder:
```json
{
  "host": "192.168.2.130",
  "port": 3307,
  "user": "root",
  "password": "Admin@123",
  "database": "algo_relative_strength"
}
```

Then run on your Windows Laptop:
```powershell
python run_dashboard.py
```
The dashboard connects immediately, displays live relative strength curves, momentum radar, and heatmaps without saving anything locally!

---

## 6. Running the Autonomous Collector on Linux PC (24/7)

Since standard user accounts on the Linux PC do not have `sudo` privileges, `run_collector.py` runs inside `tmux`, `screen`, or `nohup`:

### Recommended: Run inside `tmux`
```bash
# 1. Start tmux session
tmux new -s collector

# 2. Go to project directory
cd ~/AlgoTradingPythonProjects/projects/06_live_relative_strength_and_heatmap_dashboard

# 3. Launch collector
python run_collector.py

# 4. Detach session (leaves it running 24/7 in background)
# Press Ctrl + B, then D
```

To re-attach and check logs anytime:
```bash
tmux attach -t collector
```

---

## 7. Single-Device Local Fallback

If you ever want to run both the collector and GUI dashboard locally on your laptop:
1. Delete or rename `connection_config.json`.
2. Both scripts will automatically default to `localhost:3306` with zero configuration required.
