# Cobra Jogger - SCARA Robot Control

Python GUI application for jogging an **Adept Cobra 600 SCARA robot** using a gamepad (PS4/Xbox controller) via serial communication with the V+ controller.

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 🎮 Features

- **Gamepad Control**: Use PS4 or Xbox controller for intuitive jogging
- **Deadman Safety**: Requires button hold for motion (safety feature)
- **Real-time Control**: ~20 Hz update rate for smooth motion
- **Dual Control Modes**:
  - **Mode 1** (Current): Direct monitor commands via terminal
  - **Mode 2** (Advanced): V+ jog server with checksum verification
- **Configurable Speeds**: Adjustable XY, Z, and rotation speeds
- **Power Management**: Enable/disable servos and calibrate from GUI

---

## 📋 Requirements

### Hardware
- Adept Cobra 600 SCARA robot with V+ controller
- RS-232 serial cable (likely null-modem configuration)
- PS4 or Xbox controller (wired or Bluetooth)
- Windows/Linux/macOS PC

### Software
```bash
pip install pyserial pygame
```

- Python 3.7+
- pyserial (serial communication)
- pygame (gamepad input)
- tkinter (included with Python, GUI framework)

---

## 🚀 Quick Start

### 1. Hardware Setup
1. Connect PC to V+ controller's **terminal port** via RS-232
   - Default settings: **9600 baud, 8-N-1**
   - May require null-modem adapter
2. Connect PS4/Xbox controller via USB or Bluetooth
3. Power on robot and controller

### 2. Run the Application
```bash
python cobra_jogger.py
```

### 3. Connect and Calibrate
1. Select serial port from dropdown
2. Click **Connect**
3. Click **ENABLE POWER**
4. Click **CALIBRATE** (ensure clear workspace!)
5. Adjust speed sliders to conservative values initially

### 4. Start Jogging
- **Hold RB (PS4: R1) or A button** as deadman switch
- **Left stick**: X/Y motion
- **Right trigger/Left trigger**: Z up/down
- **Right stick (X-axis)**: Theta rotation

---

## 🎮 Controller Mapping

### PS4 Controller (via Bluetooth)
| Input | Function |
|-------|----------|
| **R1 or X** | Deadman (hold to enable motion) |
| **Left Stick** | X/Y jogging (right/forward) |
| **L2 / R2** | Z down / Z up |
| **Right Stick (X)** | Theta rotation |
| **Triangle** | Enable power |
| **Square** | Calibrate |
| **Circle** | Disable power (soft E-stop) |

### Xbox Controller
| Input | Function |
|-------|----------|
| **RB or A** | Deadman (hold to enable motion) |
| **Left Stick** | X/Y jogging (right/forward) |
| **LT / RT** | Z down / Z up |
| **Right Stick (X)** | Theta rotation |
| **Y** | Enable power |
| **X** | Calibrate |
| **B** | Disable power (soft E-stop) |

---

## ⚙️ Control Modes

### Mode 1: Monitor Streaming (Current Implementation)

**How it works:**
- Python app sends `EXECUTE DMOVE(dx,dy,dz,dθ)` commands to V+ monitor
- Direct control via terminal/dot prompt
- Simple, no controller programming required

**Pros:**
- Zero setup on controller side
- Easy to debug
- Works immediately

**Cons:**
- Not hard real-time
- Higher latency (~50-100ms)
- Limited throughput

**Recommended for:** Testing, low-speed operations, initial setup

---

### Mode 2: V+ Jog Server with Checksum (Coming Soon)

**How it works:**
- V+ program runs on controller, reading velocity packets from SERIAL:2
- Python sends velocity setpoints at 20-50 Hz with CRC16 checksum
- Controller handles motion loop internally

**Pros:**
- Lower latency (<10ms)
- Smoother motion
- Real-time performance
- Error detection via checksum

**Cons:**
- Requires loading V+ program to controller
- More complex setup

**Recommended for:** Production use, high-speed operations, precise control

#### Protocol Specification (Mode 2)

**Text Protocol (easier debugging):**
```
Format: V <vx> <vy> <vz> <vtheta> *<CRC16>\r\n
Example: V 100.50 -50.25 0.00 5.50 *A3F2\r\n

vx, vy, vz: velocities in mm/s
vtheta: angular velocity in deg/s
CRC16: 16-bit CRC checksum in hex
```

**Binary Protocol (faster, recommended):**
```
[STX] [vx:float32] [vy:float32] [vz:float32] [vtheta:float32] [CRC16:uint16] [ETX]

STX = 0x02 (start of text)
ETX = 0x03 (end of text)
Total packet size: 20 bytes
```

---

## 🖥️ V+ Program Editor (New!)

**No more 25-year-old Adept software!** Edit and upload V+ programs with a modern Python tool.

```bash
python vplus_editor.py
```

**Features:**
- ✅ Edit V+ programs in modern text editor
- ✅ Upload/download programs over serial
- ✅ List and delete programs on controller
- ✅ Real-time monitor output
- ✅ Save/load local files
- ✅ No legacy software required!

See **[VPLUS_EDITOR_GUIDE.md](VPLUS_EDITOR_GUIDE.md)** for complete documentation.

---

## 🛠️ Configuration

### Serial Settings
- **Baud rate**: 9600 (default), configurable to 19200, 38400, 57600, 115200
- **Data bits**: 8
- **Parity**: None
- **Stop bits**: 1

### Speed Limits (configurable via GUI)
- **XY speed**: 10-600 mm/s (default: 200 mm/s)
- **Z speed**: 5-300 mm/s (default: 100 mm/s)
- **Theta**: 5-90 deg/s (default: 30 deg/s)

### Safety Parameters (hardcoded)
- **Deadband**: 0.15 (15% stick deadzone)
- **Step clamp**: ±5 mm/deg per command
- **Update rate**: 20 Hz (50ms period)

---

## 🔧 Advanced: Setting Up V+ Jog Server (Mode 2)

### 1. Create V+ Program

Transfer this program to your controller (see `vplus_jog_server.v` for complete code):

```vplus
.PROGRAM jogserver
  AUTO
  SPEED 100 ALWAYS
  ACCEL 100, 100
  
  TYPE "Jog Server Ready"
  
  WHILE TRUE DO
    ; Read velocity packet from SERIAL:2
    $packet = ""
    READ SERIAL(2) $packet
    
    ; Validate checksum and parse
    IF CHECKSUM_OK($packet) THEN
      vx = FLOAT(FIELD($packet, 2))
      vy = FLOAT(FIELD($packet, 3))
      vz = FLOAT(FIELD($packet, 4))
      vtheta = FLOAT(FIELD($packet, 5))
      
      ; Execute incremental move (50 Hz = 0.02s)
      DMOVE(vx*0.02, vy*0.02, vz*0.02, vtheta*0.02)
    END
  END
.END
```

### 2. Configure Serial Port 2
```vplus
; At V+ monitor prompt:
SERIAL 2, 115200, 8, 1, 0  ; 115200 baud, 8 data bits, 1 stop, no parity
```

### 3. Switch Python App to Mode 2
In the GUI:
1. Select "V+ Jog Server" mode from dropdown
2. Ensure SERIAL:2 is configured on controller
3. Click Connect

---

## 🧪 Testing Procedure

1. **Initial Test** (Mode 1, low speed):
   - XY: 50 mm/s, Z: 30 mm/s, Theta: 10 deg/s
   - Verify all axes respond correctly
   - Check E-stop functionality

2. **Workspace Limits**:
   - Slowly jog to confirm workspace boundaries
   - Note any singularities or restricted zones

3. **Speed Ramp-up**:
   - Gradually increase speeds
   - Monitor for vibration or lag
   - Don't exceed 400 mm/s for XY initially

4. **Mode 2 Validation** (if implemented):
   - Compare smoothness vs Mode 1
   - Verify checksum error handling
   - Test at higher update rates (50 Hz)

---

## ⚠️ Safety Guidelines

- **Always** start with low speeds
- **Always** keep robot workspace clear
- **Always** have E-stop button accessible
- **Never** reach into robot workspace during operation
- **Monitor** for unusual sounds or vibrations
- **Stop immediately** if unexpected behavior occurs

---

## 📝 Troubleshooting

### Controller won't connect
- Check serial cable (try null-modem adapter)
- Verify baud rate matches controller settings
- Ensure controller is in monitor mode (dot prompt visible)

### Gamepad not detected
- Check USB connection or Bluetooth pairing
- Run `pygame.joystick.get_count()` to verify detection
- Try unplugging/replugging controller

### Laggy or jerky motion
- Lower jog speeds
- Check serial buffer isn't overflowing
- Consider upgrading to Mode 2 (V+ jog server)

### Robot doesn't move
- Verify power is enabled (`ENABLE POWER`)
- Check deadman button is held
- Confirm calibration is complete
- Check for error messages in V+ terminal

---

## 📚 Documentation & Resources

### V+ Documentation
- Adept V+ Language Reference (1998)
- Monitor commands: `ENABLE POWER`, `DISABLE POWER`, `CALIBRATE`, `EXECUTE`
- Motion commands: `MOVE`, `DMOVE`, `SPEED`, `ACCEL`

### Serial Communication
- Terminal port: V+ monitor interface
- SERIAL:2 port: User-programmable I/O (for Mode 2)

---

## 🔮 Future Enhancements

- [ ] Mode 2: V+ jog server with checksum implementation
- [ ] Touch probe integration for work coordinate setup
- [ ] Position logging and playback
- [ ] Multi-robot support
- [ ] Web-based remote control interface
- [ ] Force feedback via controller rumble
- [ ] Collision detection zones

---

## 📄 License

MIT License - Feel free to modify and distribute

---

## 🤝 Contributing

Contributions welcome! Please test thoroughly on a safe setup before submitting PRs.

---

## 👤 Author

SCARA Control Project

**Robot:** Adept Cobra 600  
**Controller:** V+ (1998 vintage)  
**Gamepad:** PS4 DualShock 4 / Xbox compatible

---

*Last updated: 2025-10-28*
