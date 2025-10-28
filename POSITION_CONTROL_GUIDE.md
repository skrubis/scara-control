# Position Control & Soft Limit Handling Guide

## 🎯 Your Questions Answered

### Question 1: How are soft limits handled?

**Current problem with incremental jogging:**
- ❌ Robot hits limit and stops
- ❌ Python keeps sending velocity commands (doesn't know!)
- ❌ No feedback loop
- ❌ Commands accumulate in buffer

**What should happen:**
- ✅ Query robot position periodically
- ✅ Detect when at limit (position not changing)
- ✅ Stop sending commands in that direction
- ✅ Allow reverse motion to leave limit

### Question 2: Can you send absolute commands?

**YES!** Absolute positioning is actually **better** for continuous control:
- ✅ Like 3D printer G-code
- ✅ No accumulation errors
- ✅ Soft limits handled by controller
- ✅ Smoother motion
- ✅ Always knows target

---

## 🔄 Three Control Modes Compared

### Mode 1: Incremental (DMOVE) - Original

**How it works:**
```vplus
DMOVE(dx, dy, dz, dtheta)  ; Move by delta
```

**Pros:**
- ✅ Simple
- ✅ Works immediately
- ✅ No position needed

**Cons:**
- ❌ No feedback
- ❌ Accumulates errors
- ❌ Bad at soft limits
- ❌ Can lose track of position

**Soft limit behavior:**
```
1. Jog forward (+X)
2. Hit limit at X=500
3. Robot stops, but Python doesn't know!
4. Python keeps sending DMOVE(+5,0,0,0)
5. Commands queue up
6. When you release stick, robot is stuck
```

---

### Mode 2: Absolute Positioning (MOVE) - New! ⭐

**How it works:**
```vplus
; Continuously update target position
target_x = current_x + (joystick_x * speed * dt)
MOVE(TRANS(target_x, target_y, target_z, target_theta))
```

**Pros:**
- ✅ Smooth continuous motion
- ✅ Controller handles limits automatically
- ✅ No command accumulation
- ✅ Like 3D printer (G1 X100 Y50)

**Cons:**
- ⚠️ Need to query position periodically
- ⚠️ Slightly more complex

**Soft limit behavior:**
```
1. Jog forward (+X)
2. Hit limit at X=500
3. Controller refuses MOVE beyond 500
4. Robot stays at 500 (correct!)
5. Joystick still updates target_x to 505, 510...
6. When you reverse joystick, target_x becomes 505, 500, 495...
7. Robot starts moving backward smoothly ✓
```

---

### Mode 3: Position Feedback with Limits - Best! 🌟

**How it works:**
```python
1. Query position every 500ms: WHERE
2. Update target based on joystick
3. Check if at soft limit (position not changing)
4. If at limit, only allow reverse motion
5. Display current position in GUI
```

**Pros:**
- ✅ ✅ Full position awareness
- ✅ ✅ Detects limits automatically
- ✅ ✅ Prevents overshoot
- ✅ ✅ Shows position in GUI
- ✅ ✅ Safest option

**Cons:**
- ⚠️ Requires position queries
- ⚠️ Depends on WHERE command support

**Implementation:** See `cobra_jogger_absolute.py`

---

## 📊 V+ Position Commands Reference

### Query Position

```vplus
WHERE               ; Returns current position
; Output: TRANS(100.5, 200.3, 50.0, 15.2)
; Or: X: 100.5 Y: 200.3 Z: 50.0 T: 15.2
```

### Absolute Moves

```vplus
; Define position
SET location1 = TRANS(100, 200, 50, 0)

; Move to absolute position
MOVE location1

; Or inline:
MOVE TRANS(100, 200, 50, 0)

; Can also use EXECUTE for one-time moves:
EXECUTE MOVE(TRANS(100, 200, 50, 0))
```

### Incremental Moves

```vplus
; Move by delta
DMOVE(10, 5, 0, 0)  ; +10mm X, +5mm Y

; Relative to current location
APPRO location1, 50  ; Approach 50mm above
DEPART 50            ; Depart 50mm up
```

### Check Limits

```vplus
; Query limit status
STATUS              ; Shows error flags
; Look for "LIMIT" or "RANGE" errors

; Set custom limits (if supported)
JRANGE minx, maxx, miny, maxy, minz, maxz
```

---

## 🚀 Implementation: Absolute Mode

### Python Side (cobra_jogger_absolute.py)

```python
# 1. Query position periodically
def query_position(self):
    self.send_cmd("WHERE")
    time.sleep(0.1)
    response = self.read_nonblocking()
    # Parse: TRANS(x, y, z, theta)
    # Update self.current_position

# 2. Update target based on joystick
target_x += joystick_x * speed * dt
target_y += joystick_y * speed * dt
target_z += joystick_z * speed * dt

# 3. Send absolute command
cmd = f"EXECUTE MOVE(TRANS({target_x},{target_y},{target_z},{target_theta}))"
send_cmd(cmd)

# 4. Display position in GUI
label.config(text=f"X: {current_x:7.2f}  Y: {current_y:7.2f}  ...")
```

### V+ Side (for Mode 2 jog server)

```vplus
.PROGRAM jogserver_absolute

  AUTO
  TYPE "Absolute Position Jog Server"
  
  ; Get initial position
  current_location = HERE
  
  WHILE TRUE DO
    ; Read velocity packet
    READ SERIAL(2) $packet
    
    ; Parse velocities
    vx = ...
    vy = ...
    vz = ...
    
    ; Update target position
    target_x = TRANSFORM(current_location, 0) + vx * dt
    target_y = TRANSFORM(current_location, 1) + vy * dt
    target_z = TRANSFORM(current_location, 2) + vz * dt
    target_theta = TRANSFORM(current_location, 3) + vtheta * dt
    
    ; Move to target (controller handles limits)
    SET target_loc = TRANS(target_x, target_y, target_z, target_theta)
    MOVE target_loc NOWAIT
    
    ; Update current
    current_location = target_loc
    
    DELAY 0.02
  END
.END
```

---

## 🔍 Detecting Soft Limits

### Method 1: Position Delta Check

```python
# Query position twice
pos1 = query_position()  # X: 498
time.sleep(0.1)
# Send DMOVE(+5, 0, 0, 0)
time.sleep(0.1)
pos2 = query_position()  # X: 500 (didn't move full +5!)

# Detect limit
if abs(pos2['x'] - pos1['x']) < 1.0:  # Expected +5, got +2
    print("Hit X+ soft limit!")
    # Stop sending positive X commands
```

### Method 2: Error Status Check

```python
# Send STATUS command
response = send_command("STATUS")

# Look for error flags
if "LIMIT" in response or "RANGE" in response:
    print("At soft limit!")
    # Parse which axis
```

### Method 3: Command Response

```python
# Some controllers echo errors after failed moves
send_cmd("DMOVE(100, 0, 0, 0)")  # Try to move far
response = read_response()

if "ERROR" in response or "LIMIT" in response:
    print("Move rejected - at limit")
```

---

## 🎮 3D Printer Analogy

**G-code (3D Printer):**
```gcode
G1 X100 Y50 Z10 F3000    ; Move to absolute position at 3000 mm/min
G1 X110 Y55 Z10          ; Move to next position
```

**V+ Equivalent (Absolute Mode):**
```vplus
MOVE TRANS(100, 50, 10, 0)   ; Move to position
MOVE TRANS(110, 55, 10, 0)   ; Next position
```

**Continuous jogging like 3D printer:**
```python
# Update target continuously based on joystick
while jogging:
    target_x += joystick_x * speed * dt
    target_y += joystick_y * speed * dt
    
    # Send absolute position (like G1 command)
    gcode = f"G1 X{target_x} Y{target_y}"  # 3D printer
    vplus = f"MOVE TRANS({target_x},{target_y},z,theta)"  # Robot
    
    send(vplus)
```

**This is exactly what `cobra_jogger_absolute.py` does!**

---

## ✅ Recommended Approach

### For Best Results:

1. **Use Absolute Mode** (`cobra_jogger_absolute.py`)
   - Smoother motion
   - Better limit handling
   - Position display

2. **Query position periodically** (every 500ms)
   - Detect actual position
   - Update GUI
   - Sync target when deadman released

3. **Let controller handle limits**
   - Controller knows workspace
   - Won't execute beyond limits
   - Safer than Python logic

4. **Display current position**
   - User sees where robot is
   - Can detect stuck conditions
   - Better situational awareness

---

## 🧪 Testing Procedure

### Test Soft Limit Handling

```python
# 1. Run cobra_jogger_absolute.py
python cobra_jogger_absolute.py

# 2. Connect and enable
# 3. Select "Absolute" mode
# 4. Jog slowly toward known limit
# 5. Watch position display
# 6. When position stops changing → at limit
# 7. Reverse joystick → should move away smoothly
```

### Test Position Accuracy

```python
# 1. Note starting position: X: 100.0
# 2. Jog +X for 5 seconds
# 3. Note ending position: X: 150.0
# 4. Difference: 50.0mm
# 5. Compare to speed setting (e.g., 100 mm/s × 0.5 = 50mm) ✓
```

---

## 📝 Code Comparison

### Old (Incremental, No Feedback)

```python
# Send delta, hope for the best
dx = joystick_x * speed * dt
DMOVE(dx, 0, 0, 0)
# ❌ Don't know if it actually moved
# ❌ Don't know current position
# ❌ Can't detect limits
```

### New (Absolute, With Feedback)

```python
# Query position
current_pos = query_position()  # X: 495

# Update target
target_x = current_pos['x'] + joystick_x * speed * dt  # 495 + 5 = 500

# Move to target
MOVE TRANS(target_x, y, z, theta)

# Controller response:
# If target beyond limit → clamps to limit
# If valid → moves smoothly
# ✅ Always know where robot is
# ✅ Limits handled automatically
```

---

## 🎯 Summary

### Your Questions:

**Q1: How are soft limits handled?**
- **Old way**: Not well - commands accumulate, robot gets stuck
- **New way**: Controller handles limits in absolute mode
- **Best way**: Position feedback + absolute mode + GUI display

**Q2: Can you send absolute commands?**
- **YES!** Use `MOVE TRANS(x,y,z,theta)`
- **Better** than incremental for continuous control
- **Just like** 3D printer G-code G1 commands
- **See**: `cobra_jogger_absolute.py`

### Tools Available:

1. **cobra_jogger.py** - Simple incremental (works but basic)
2. **cobra_jogger_v2.py** - Dual mode with checksums
3. **cobra_jogger_absolute.py** - Absolute mode with position feedback ⭐ **NEW!**

Try the new absolute mode - it solves both your concerns!

---

*"Think of it like a 3D printer: send target positions continuously, controller handles the physics."* 🎯
