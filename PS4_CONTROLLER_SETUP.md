# PS4 Controller Setup Guide

This guide covers connecting and using your **PS4 DualShock 4** controller with the Cobra Jogger application.

---

## 🎮 Connection Methods

### Method 1: Bluetooth (Recommended)

**Advantages:**
- Wireless, no cable needed
- Full range of motion
- Safer (can move away from robot quickly)

**Steps for Windows:**

1. **Put PS4 controller in pairing mode:**
   - Hold **PS button** + **Share button** for 3-5 seconds
   - Light bar will start flashing white

2. **On Windows:**
   - Open **Settings** → **Devices** → **Bluetooth**
   - Click **Add Bluetooth or other device**
   - Select **Bluetooth**
   - Look for **Wireless Controller**
   - Click to pair
   - Wait for "Connected" status

3. **Verify connection:**
   - Light bar should turn solid (blue/white)
   - Run `cobra_jogger_v2.py`
   - Should show "Gamepad connected"

**Troubleshooting Bluetooth:**
- If controller won't pair, reset it:
  - Use paperclip to press reset button (small hole on back)
  - Hold for 5 seconds
  - Try pairing again
- Install **DS4Windows** if Windows doesn't recognize controller natively
- Check Windows Device Manager for "Wireless Controller" entry

### Method 2: USB Cable

**Advantages:**
- More reliable (no wireless dropouts)
- No battery concerns
- Lower latency

**Steps:**

1. Connect PS4 controller via **USB micro cable**
2. Windows should automatically install drivers
3. Run `cobra_jogger_v2.py`
4. Should show "Gamepad connected" immediately

**Note:** Some cheap USB cables are charge-only and don't support data. Use the original Sony cable or a known data cable.

---

## 🕹️ Button Mapping

### PS4 DualShock 4 Layout

```
        [L2]                                    [R2]
        [L1]                                    [R1]

                    [△]
               [□]  [○]
                    [✕]

        [Left Stick]            [Right Stick]
```

### Cobra Jogger Controls

| PS4 Button | Function | Details |
|------------|----------|---------|
| **R1 (Right Bumper)** | Deadman | Hold to enable motion |
| **✕ (Cross)** | Deadman (alt) | Alternative deadman button |
| **Left Stick** | X/Y Jogging | Left/right = X, Up/down = Y |
| **L2 (Left Trigger)** | Z Down | Analog trigger, smooth control |
| **R2 (Right Trigger)** | Z Up | Analog trigger, smooth control |
| **Right Stick (X-axis)** | Theta Rotation | Left/right only |
| **△ (Triangle)** | Enable Power | Sends ENABLE POWER command |
| **□ (Square)** | Calibrate | Sends CALIBRATE command |
| **○ (Circle)** | Disable Power | Soft E-stop, DISABLE POWER |
| **PS Button** | (Not used) | Used for pairing/system menu |
| **Share** | (Not used) | - |
| **Options** | (Not used) | - |

---

## 🎚️ Axis Details

### Stick Behavior

**Left Stick:**
- **X-axis (left/right):** Robot X motion
  - Push right → Robot moves +X
  - Push left → Robot moves -X
- **Y-axis (up/down):** Robot Y motion  
  - Push up → Robot moves +Y (forward)
  - Push down → Robot moves -Y (backward)

**Right Stick:**
- **X-axis only:** Theta rotation
  - Push right → Rotate clockwise (+θ)
  - Push left → Rotate counter-clockwise (-θ)
- **Y-axis:** Not used

### Trigger Behavior

**L2 (Left Trigger):**
- Analog: 0% (released) to 100% (fully pressed)
- Controls Z-axis down velocity
- Light press = slow down
- Full press = max speed down

**R2 (Right Trigger):**
- Analog: 0% (released) to 100% (fully pressed)
- Controls Z-axis up velocity
- Light press = slow up
- Full press = max speed up

**Combined Z Control:**
- Both triggers released = no Z motion
- Press R2 only = move up
- Press L2 only = move down
- Both pressed simultaneously = canceled out (no motion)

---

## ⚙️ Axis Calibration

If the controller feels "drifty" or axes are inverted:

### Check Deadzones

The app has a built-in **15% deadband** to prevent drift. Adjust if needed:

```python
# In cobra_jogger_v2.py, JogLoop class
self.deadband = 0.15  # Change to 0.20 for larger deadzone
```

### Invert Axes

If motion feels backwards:

```python
# In Gamepad.run() method

# To invert X:
state.x = -lx  # Add minus sign

# To invert Y (currently already inverted):
state.y = ly  # Remove minus sign

# To invert Z:
z = -z  # Add after calculation

# To invert Theta:
state.theta = -rx  # Add minus sign
```

### Test Axis Mapping

Run this diagnostic script:

```python
import pygame

pygame.init()
pygame.joystick.init()

joy = pygame.joystick.Joystick(0)
joy.init()

print(f"Controller: {joy.get_name()}")
print(f"Axes: {joy.get_numaxes()}")
print(f"Buttons: {joy.get_numbuttons()}")

try:
    while True:
        pygame.event.pump()
        print("\n" + "="*50)
        print("AXES:")
        for i in range(joy.get_numaxes()):
            print(f"  Axis {i}: {joy.get_axis(i):+.3f}")
        print("\nBUTTONS:")
        pressed = [str(i) for i in range(joy.get_numbuttons()) if joy.get_button(i)]
        print(f"  Pressed: {', '.join(pressed) if pressed else 'none'}")
        
        import time
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nExiting...")
```

**Expected output for PS4 controller:**
```
Axes:
  Axis 0: Left stick X (-1 left, +1 right)
  Axis 1: Left stick Y (-1 up, +1 down)
  Axis 2: L2 trigger (-1 released, +1 pressed)
  Axis 3: Right stick X (-1 left, +1 right)
  Axis 4: Right stick Y (-1 up, +1 down)
  Axis 5: R2 trigger (-1 released, +1 pressed)

Buttons:
  0 = ✕ (Cross)
  1 = ○ (Circle)
  2 = □ (Square)
  3 = △ (Triangle)
  4 = Share
  5 = PS button
  6 = Options
  7 = L3 (left stick click)
  8 = R3 (right stick click)
  9 = L1
  10 = R1
```

**Note:** Button numbers may vary by driver. The app uses:
- Button 5 or 0 = Deadman (R1 or ✕)
- Button 3 = Enable (△)
- Button 2 = Calibrate (□)
- Button 1 = Disable (○)

---

## 🔋 Battery Management

### Battery Level Check

PS4 controller battery status:
- **Solid blue:** Good charge
- **Blinking orange:** Low battery
- **Pulsing orange:** Charging via USB

### Extending Battery Life

1. **Reduce light bar brightness:**
   - Hold PS button
   - Go to Accessories → Controllers
   - Adjust brightness or turn off

2. **Turn off controller when not in use:**
   - Hold PS button for 10 seconds
   - Or let it auto-sleep after 10 minutes

3. **Use USB cable during long sessions**

### Battery Replacement

If battery life is poor:
- Genuine Sony replacement batteries available
- Requires disassembly (YouTube guides available)
- Or use wired mode exclusively

---

## 🐛 Common Issues

### Issue: Controller connects but app says "not connected"

**Solution:**
1. Close and reopen the app
2. pygame may need to reinitialize
3. Try unplugging/replugging (USB) or disconnecting/reconnecting (Bluetooth)

### Issue: Input lag or stuttering

**Possible causes:**
1. **Bluetooth interference:**
   - Move away from Wi-Fi routers, microwaves
   - Use 5 GHz Wi-Fi instead of 2.4 GHz (same band as Bluetooth)
   - Switch to USB cable

2. **USB cable quality:**
   - Use original Sony cable
   - Try different USB port (USB 3.0 recommended)

3. **PC performance:**
   - Close background applications
   - Check CPU usage in Task Manager

### Issue: Axes are swapped or wrong

**Solution:**
- See "Test Axis Mapping" above
- Controller driver may be different
- Install DS4Windows for consistent mapping

### Issue: Deadman doesn't work

**Check:**
1. Are you holding R1 or ✕?
2. Check button mapping with diagnostic script
3. Button 5 or 0 should be pressed
4. Try other buttons if mapping is different

### Issue: Light bar stays orange

**Meaning:** Controller is in pairing mode or charging
- If charging, it's normal
- If not charging, unpair and re-pair
- Press PS button to exit pairing mode

---

## 🎮 Alternative Controllers

If PS4 controller doesn't work or you prefer other options:

### Xbox Controller

- Generally better Windows support
- Native drivers, no extra software needed
- Same mapping, slightly different button names

### Generic USB Gamepad

- Should work with pygame
- May require button remapping in code
- Test with diagnostic script first

### Steam Controller

- Requires Steam running
- Configure in Steam Big Picture mode
- Can emulate Xbox controller

---

## 🔐 Safety Tips

1. **Always keep one hand on controller, one near E-stop**
2. **Release deadman immediately if unexpected motion**
3. **Don't walk away while controller is connected**
4. **Be aware of Bluetooth range (10m typical)**
5. **Watch for low battery warnings**
6. **Test in free space before production work**

---

## 📝 Configuration Recommendations

### For Fine Work (High Precision)

**Settings:**
- XY speed: 50 mm/s
- Z speed: 30 mm/s
- Theta: 10 deg/s
- Deadband: 0.20 (larger, steadier)

**Technique:**
- Use light stick movements
- Take advantage of analog triggers
- Work slowly and deliberately

### For Rough Positioning (Fast Movement)

**Settings:**
- XY speed: 300 mm/s
- Z speed: 150 mm/s
- Theta: 45 deg/s
- Deadband: 0.15 (standard)

**Technique:**
- Use full stick deflection
- Quick movements to get close
- Switch to fine mode for final positioning

---

## 🎯 Pro Tips

1. **Practice without power first:**
   - Connect controller
   - Move sticks and observe readouts
   - Get feel for control before enabling robot

2. **Use consistent grip:**
   - Hold controller the same way every time
   - Muscle memory develops quickly
   - Consider controller grips/attachments

3. **Map your workspace:**
   - Know where limits are
   - Mark safe zones with tape
   - Never jog beyond visual line of sight

4. **Master the deadman:**
   - Keep thumb on R1 at all times
   - Practice instant release
   - Make it a reflex

5. **Use both deadman options:**
   - R1 for jogging
   - ✕ for teaching points (easier to hold and press buttons)

---

## 📊 Comparison: PS4 vs Xbox

| Feature | PS4 DualShock 4 | Xbox Controller |
|---------|-----------------|-----------------|
| **Battery** | Built-in rechargeable | AA or rechargeable pack |
| **Bluetooth** | Native | Xbox One S+ only |
| **Windows Support** | Needs DS4Windows (optional) | Native, excellent |
| **Linux Support** | Excellent | Good |
| **Ergonomics** | Smaller, symmetrical sticks | Larger, offset sticks |
| **Touchpad** | Yes (not used by app) | No |
| **Light bar** | Yes | No |
| **Price** | ~$65 | ~$60 |

**Recommendation for this application:**
- **Xbox controller** if you're on Windows primarily
- **PS4 controller** if you use Bluetooth and have one already

Both work excellently with the Cobra Jogger!

---

## 🆘 Support

If you're still having issues:

1. **Check pygame documentation:** https://www.pygame.org/docs/
2. **Test controller with other apps:**
   - Steam Big Picture mode
   - HTML5 gamepad tester (browser)
3. **Try DS4Windows:** https://ds4-windows.com/
4. **Update controller firmware** (via PS4 console)

---

*Enjoy wireless robot control with your PS4 controller!*
