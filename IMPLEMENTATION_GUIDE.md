# Implementation Guide: Mode 2 V+ Jog Server

This guide explains how to implement and deploy the advanced V+ Jog Server mode with CRC16 checksum validation for your Adept Cobra 600 SCARA robot.

---

## 📊 Mode Comparison

| Feature | Mode 1: Monitor Streaming | Mode 2: V+ Jog Server |
|---------|--------------------------|----------------------|
| **Setup Complexity** | ✅ Simple (no controller programming) | ⚠️ Moderate (requires V+ program) |
| **Update Rate** | 20 Hz | 50 Hz |
| **Latency** | 50-100ms | <10ms |
| **Smoothness** | Good | Excellent |
| **Error Detection** | None | CRC16 checksum |
| **Real-time** | No | Yes (controller-side loop) |
| **Serial Port** | Terminal (monitor) | SERIAL(2) |
| **Baud Rate** | 9600 (default) | 115200 (recommended) |
| **Best For** | Testing, initial setup | Production, high-speed work |

---

## 🚀 Deployment Steps for Mode 2

### Step 1: Prepare V+ Program

1. **Review the V+ program**: Open `vplus_jog_server.v` in a text editor
2. **Understand the code**:
   - Main loop runs at 50 Hz
   - Reads velocity packets from SERIAL(2)
   - Validates CRC16 checksum
   - Executes DMOVE based on velocities
   - Includes watchdog timer (stops motion after 200ms timeout)

### Step 2: Transfer to Controller

**Method A: Serial transfer (if available)**
```vplus
; At V+ monitor prompt
LOAD "jogserver" FROM SERIAL(1)
; Then paste the file contents
```

**Method B: Using Adept development tools**
- Use V+ Development Environment or AdeptSight
- Load `vplus_jog_server.v` file
- Compile and transfer to controller

**Method C: Manual entry (tedious but works)**
- Connect to monitor prompt
- Type `.EDIT jogserver` to create new program
- Enter code line by line
- Save with `.END`

### Step 3: Configure Serial Port 2

At the V+ monitor prompt:
```vplus
SERIAL 2, 115200, 8, 1, 0
```

This configures SERIAL(2) for:
- 115200 baud
- 8 data bits
- 1 stop bit
- 0 = no parity

Verify with:
```vplus
STATUS SERIAL(2)
```

### Step 4: Test V+ Program

Start the jog server:
```vplus
DO jogserver
```

You should see:
```
===================================
   Cobra 600 Jog Server v1.0
===================================
Protocol: V vx vy vz vtheta *CRC16
Cycle time: 0.02 seconds
Timeout: 0.2 seconds

Jog Server Ready - Waiting for commands...
```

To stop:
```vplus
ABORT
```

### Step 5: Configure Python Application

1. Run `cobra_jogger_v2.py`
2. Select **"V+ Jog Server"** from the Mode dropdown
3. Baud rate automatically changes to **115200**
4. Select correct COM port (the one connected to SERIAL(2))
5. Click **Connect**

### Step 6: Verify Communication

1. Hold deadman button (RB/R1)
2. Gently move left stick
3. Robot should respond smoothly
4. Check stats display for packet count

**Expected behavior:**
- Smooth, responsive motion
- Higher update rate than Mode 1
- No visible "stuttering"

---

## 🔍 Protocol Details

### Packet Format

**Text Protocol (human-readable):**
```
V <vx> <vy> <vz> <vtheta> *<CRC16>\r\n

Example: V 100.50 -50.25 0.00 5.50 *A3F2\r\n
```

**Fields:**
- `V` = packet identifier
- `vx, vy, vz` = velocities in mm/s (float)
- `vtheta` = angular velocity in deg/s (float)
- `*` = checksum delimiter
- `CRC16` = 4-digit hex CRC-16-CCITT checksum
- `\r\n` = CR+LF terminator

### CRC16 Calculation

**Algorithm: CRC-16-CCITT**
- Polynomial: 0x1021
- Initial value: 0xFFFF
- Calculated over: `"V vx vy vz vtheta "` (everything before `*`)

**Python implementation:**
```python
def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

# Usage
data_str = "V 100.50 -50.25 0.00 5.50 "
crc = crc16_ccitt(data_str.encode('ascii'))
packet = f"{data_str}*{crc:04X}\r\n"
```

### Watchdog Timer

The V+ program includes a safety watchdog:
- If no valid packet received for **200ms**, motion stops
- Prevents runaway if PC crashes or cable disconnects
- Python app sends zero-velocity packets when deadman is released

---

## 🧪 Testing Procedure

### 1. Bench Test (No Robot Motion)

**Objective:** Verify communication without moving robot

```python
# Test script to verify protocol
import serial
import time

def crc16_ccitt(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

# Connect to SERIAL(2)
ser = serial.Serial('COM3', 115200, timeout=0.1)

# Send test packet
data_str = "V 0.00 0.00 0.00 0.00 "
crc = crc16_ccitt(data_str.encode('ascii'))
packet = f"{data_str}*{crc:04X}\r\n"

for i in range(10):
    ser.write(packet.encode('ascii'))
    print(f"Sent: {packet.strip()}")
    time.sleep(0.1)

ser.close()
```

**Expected result:**
- V+ program receives packets
- Packet count increases
- No checksum errors

### 2. Low-Speed Motion Test

**Settings:**
- XY speed: 50 mm/s
- Z speed: 30 mm/s
- Theta: 10 deg/s

**Actions:**
1. Enable power
2. Calibrate
3. Hold deadman
4. Gently move left stick X-axis
5. Verify smooth X-axis motion
6. Test all axes individually

### 3. Response Time Test

**Compare Mode 1 vs Mode 2:**
1. Start in Mode 1
2. Hold deadman, move stick quickly
3. Note motion lag
4. Switch to Mode 2
5. Repeat same motion
6. Motion should feel more responsive

### 4. Checksum Error Test

**Deliberately corrupt packets:**
```python
# Modify Python code temporarily
# Comment out CRC calculation
# packet = f"V {vx:.2f} {vy:.2f} {vz:.2f} {vtheta:.2f} *0000\r\n"
```

**Expected result:**
- V+ program rejects packets
- Error count increases
- Robot doesn't move

---

## ⚠️ Troubleshooting

### Problem: V+ program won't load

**Solutions:**
- Check syntax (V+ is case-sensitive)
- Verify your V+ version supports all functions
- Some older controllers may not have bitwise operations (XOR, AND, SHL)
- Try loading in sections to isolate errors

### Problem: "SERIAL(2) not available"

**Solutions:**
- Your controller may only have one serial port
- Check manual for available serial ports
- May need to use SERIAL(1) with mode-switching logic
- Consider hardware upgrade if SERIAL(2) unavailable

### Problem: Robot moves but jerky

**Possible causes:**
1. **Baud rate too low** → Increase to 115200
2. **Cable issues** → Check cable quality, use shielded cable
3. **PC performance** → Close background apps, use real-time priority
4. **Cycle time mismatch** → Verify dt values match (0.02s = 50 Hz)

**Solutions:**
```vplus
; In V+ program, try slower cycle time
cycle_time = 0.05  ; 20 Hz instead of 50 Hz
```

### Problem: Many CRC errors

**Possible causes:**
1. **Electrical noise** → Use shielded cable, ferrite beads
2. **Baud rate mismatch** → Verify both sides at 115200
3. **Cable too long** → Keep under 15 feet (5m) for RS-232
4. **Python CRC bug** → Verify with known test vectors

**Test CRC calculation:**
```python
# Known test vector for CRC-16-CCITT
test_data = b"123456789"
expected_crc = 0x29B1  # Known correct value

crc = crc16_ccitt(test_data)
assert crc == expected_crc, f"CRC failed: got {crc:04X}, expected {expected_crc:04X}"
```

### Problem: Watchdog keeps triggering

**Symptoms:**
- Motion stops every 200ms
- "WATCHDOG: Motion stopped" messages

**Solutions:**
1. **Increase timeout:**
```vplus
timeout_limit = 0.5  ; Increase from 0.2 to 0.5 seconds
```

2. **Increase Python send rate:**
```python
self.dt_mode2 = 0.01  ; 100 Hz instead of 50 Hz
```

3. **Check for serial buffer overflow:**
```vplus
; At monitor, check status
STATUS SERIAL(2)
```

---

## 🔧 Advanced Tuning

### Optimize for Speed

**Goal: Maximum responsiveness**

**V+ changes:**
```vplus
cycle_time = 0.01  ; 100 Hz
SPEED 100 ALWAYS
ACCEL 100, 100
```

**Python changes:**
```python
self.dt_mode2 = 0.01  # Match V+ cycle time
```

**Serial:**
```vplus
SERIAL 2, 230400, 8, 1, 0  ; Double baud if supported
```

### Optimize for Smoothness

**Goal: Ultra-smooth motion**

**V+ changes:**
```vplus
ACCEL 50, 50  ; Lower acceleration
```

**Add acceleration ramping:**
```vplus
; In main loop, smooth velocity changes
vx_target = <parsed from packet>
vx = vx + (vx_target - vx) * 0.3  ; 30% per cycle
```

### Add Position Limits

**Prevent collisions:**
```vplus
; After DMOVE calculation
current_x = TRANS(0, 0)  ; Get current X position
IF current_x + dx > max_x THEN
    dx = max_x - current_x
END
IF current_x + dx < min_x THEN
    dx = min_x - current_x
END
```

---

## 📈 Performance Metrics

### Expected Performance (Mode 2)

| Metric | Value |
|--------|-------|
| Update rate | 50 Hz |
| Latency (PC → robot) | 5-10ms |
| Packet loss | <0.1% |
| CRC errors | <0.01% |
| Max velocity | 500 mm/s |
| Positioning accuracy | ±0.1mm |

### Monitoring

**In Python:**
```python
# Add to GUI
self.lbl_perf = ttk.Label(self, text="Latency: -- ms")
self.lbl_perf.pack(...)

# In jog loop
start = time.time()
self.ser.send_raw(packet)
# ... measure roundtrip time
latency = (time.time() - start) * 1000
```

**In V+:**
```vplus
; Add performance logging
IF packet_count MOD 500 = 0 THEN
    TYPE "Packets: ", packet_count, " Errors: ", error_count
    TYPE "Error rate: ", (error_count / packet_count) * 100, "%"
END
```

---

## 🎓 Next Steps

Once Mode 2 is working:

1. **Add work coordinate systems**
   - Teach reference points
   - Transform jog commands to work frame

2. **Implement force limiting**
   - Monitor motor currents
   - Stop if excessive force detected

3. **Add teach pendant simulation**
   - Teach points with gamepad
   - Save/recall positions

4. **Multi-robot support**
   - Control multiple robots
   - Coordinated motion

5. **Vision integration**
   - Add camera for visual servoing
   - Automated alignment

---

## 📚 References

- **V+ Language Reference** (Adept Technology, 1998)
- **CRC-16-CCITT Specification** (ITU-T Recommendation V.41)
- **RS-232 Serial Communication** (EIA/TIA-232)

---

## 💡 Tips

1. **Always test in free space first**
2. **Keep E-stop accessible**
3. **Start with conservative speeds**
4. **Monitor for unusual behavior**
5. **Back up your V+ programs**
6. **Document your workspace limits**
7. **Use shielded cables for reliability**
8. **Keep cables away from motors (EMI)**

---

*Good luck with your implementation! The Mode 2 setup is more complex but provides significantly better performance for production use.*
