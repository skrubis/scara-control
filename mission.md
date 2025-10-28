I have adept cobra 600 scara bot. Manual is from 1998. I could send coordinates and domove over serial to move it. Can you find documentation and all serial port control information that is available on this robot?
# Plan

1. **Quickest working path (PC-only “monitor streaming”)**
   Your Python app talks to the V+ dot-prompt over RS-232 and continuously sends small
   `EXECUTE DMOVE(dx,dy,dz,dθ)` steps while you hold a “deadman” button on the gamepad.
   Pros: zero controller programming. Cons: not hard real-time; keep speeds conservative.

2. **Best practice (tiny V+ “jog server” later)**
   Put a short V+ task on the controller that reads velocity setpoints from serial at ~20–50 Hz and does the loop on the robot side. The PC just sends setpoints. Pros: smoother, lower latency. (We can do this next if you want.)

# Ready-to-run Python GUI (Tk + pygame + pyserial)

I generated a complete app for you:

**[Download cobra_jogger.py](sandbox:/mnt/data/cobra_jogger.py)**

### What it does

* Connects to the controller’s terminal port (defaults to **9600 8-N-1**).
* Buttons: **ENABLE POWER**, **DISABLE POWER**, **CALIBRATE**.
* Gamepad jogging (Xbox-style mappings by default):

  * Hold **RB** or **A** = **deadman**.
  * **Left stick** = X/Y.
  * **Triggers** = Z (RT up, LT down).
  * **Right stick X** = θ (tool rotation).
  * **Y** = enable, **X** = calibrate, **B** = disable (soft stop).
* Sliders for XY mm/s, Z mm/s, and θ deg/s.
* Streams tiny `DMOVE` steps at ~20 Hz with deadband filtering.

### How to use

1. Wire PC ↔ controller terminal (usually needs a **null-modem** cable).
2. Run:

   ```bash
   pip install pyserial pygame
   python cobra_jogger.py
   ```
3. Pick the serial port, click **Connect**.
4. **ENABLE POWER**, **CALIBRATE** once (clear the area).
5. Hold **RB/A** and nudge the sticks/triggers to jog. Adjust speeds with sliders.

### Safety/behavior tips

* Start with tiny speeds (e.g., XY 50 mm/s, Z 30 mm/s, θ 10 deg/s).
* Because this goes through the **monitor**, keep the step rate modest (the app uses 20 Hz) and step sizes small (clamped to ±5 mm / ±5 deg per step).
* If responsiveness ever feels laggy, stop, lower speeds, or move to the **V+ jog server** approach (controller-side loop).

---

If you want, I can also provide a compact V+ “jog server” program that listens on `SERIAL:2` for velocity lines (`V vx vy vz vθ`) and runs the loop on-board—great for smoother motion.
