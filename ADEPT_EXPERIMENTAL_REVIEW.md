# Adept Experimental Repo Review — Control Notes for Cobra S600

## Overview

This document summarizes control-related knowledge from reviewing the `adept_experimental` repository (Adept Cobra S600 focus) and evaluates how it maps to our current Python-based control app. It also evaluates the V+ jog server approach and the file transfer workflow.

---

## Control Interfaces in the Repo

- **V+ Bridge Program (adept_driver/V+/adept_ros_scara.v2)**
  - Starts three TCP servers on the controller:
    - Joint commands: 11000
    - IO read/write: 11001
    - Joint/state feedback: 11002
  - Feedback loop packs joint array (10 slots, first 4 relevant for SCARA) and robot status; streaming at a fixed cadence.
  - Contains conversion logic for SCARA S600 when translating between V+ and ROS conventions:
    - Rotary joints: degrees ↔ radians.
    - Prismatic Z (J3): meters ↔ millimeters and inverted sign (ROS positive ↔ V+ negative).
  - Auto-restarts command/feedback tasks if they die.
  - Designed to work with ROS-Industrial Downloader/Streamer nodes.

- **ROS-Industrial Nodes (C++)**
  - `adept_joint_streamer_node.cpp` / `adept_joint_downloader_node.cpp`: stream/download `FollowJointTrajectory` to the controller via the V+ TCP server.
  - `adept_robot_state_node.cpp`: receives state and republishes joint states.

- **MoveIt!/URDF specifics for Cobra S600**
  - Joint names: `inner_joint`, `outer_joint`, `quill_prismatic_joint`, `quill_rotation_joint`.
  - Joint limits (velocity): inner 6.737 rad/s, outer 12.5664 rad/s, quill prismatic 1.1 m/s, quill rotation 20.944 rad/s.
  - The prismatic joint (J3) sign inversion is important when mixing V+ and external tooling.

- **IO Interface**
  - `adept_msgs/srv/AdeptIO.srv` provides simple READ/WRITE for digital IO over ROS.
  - V+ side includes an IO server (port 11001).

---

## Relevance to Our Python App (Serial, non-ROS)

- The repo’s TCP bridge is oriented to ROS-Industrial. For a pure Python/serial workflow:
  - Monitor streaming works via `EXECUTE DMOVE(dx,dy,dz,dθ)` in small steps.
  - Absolute positioning at the monitor is fragile; the safest way is still incremental `DMOVE` steps (we now use this).
  - A custom V+ jog server over `SERIAL(2)` with a simple velocity packet protocol is a solid non-ROS solution.

---

## Evaluation: V+ Jog Server (Non‑ROS)

- The included jog server (our `vplus_jog_server.v`) implements:
  - Text protocol: `V <vx> <vy> <vz> <vtheta> *<CRC16>` at ~50 Hz.
  - CRC16-CCITT verification, watchdog timeout, and ±5 step clamp per cycle.
  - Runs motion loop inside the controller using `DMOVE` increments.
- **Adequacy**: Suitable for smooth, low-latency jogging without ROS. Recommended for production jogging once verified on your controller version.
- **Notes**:
  - Ensure `SERIAL 2, 115200, 8, 1, 0` and run the V+ program (`DO jogserver`).
  - Some V+ variants may differ in string/bitwise ops; minor adjustments may be needed (parsing TIMEOUT, XOR/AND/SHL).
  - If you need IO or richer state, consider adding small status packets or a separate lightweight status V+ program.

---

## Evaluation: File Transfer

- The Python editors (our app + `vplus_editor.py`) use the V+ monitor `.EDIT <NAME>` workflow, then line-by-line upload with small delays, plus `LISTF`/`LIST` for download.
- **Adequacy**: Works reliably for small/medium programs. Tips:
  - Keep a 40–50 ms delay per line (already implemented).
  - Use `LISTF` when available for full source; fallback to `LIST` if needed.
  - Avoid uploading while other tasks are executing; ensure dot prompt is idle.

---

## Practical Controller Notes

- `DMOVE`/`MOVE` at the monitor:
  - `DMOVE` should be prefixed with `EXECUTE` when issued from the monitor.
  - `MOVE` via `EXECUTE` can fail on some firmwares/contexts; incremental `DMOVE` is more robust at the monitor.
- `WHERE` formatting can vary:
  - The controller may output multi-line tables; parse X, Y, Z and use `r` for SCARA θ.
- Z sign convention (SCARA J3):
  - V+ and external stacks can use opposite signs; verify on hardware and invert if needed.

---

## Current App Status / Changes

- Monitor streaming now sends `EXECUTE DMOVE(...)` steps with clamping.
- Absolute mode was switched to incremental `EXECUTE DMOVE(...)` steps for reliability.
- `WHERE` parser handles multi-line formats (X Y Z y p r + J1..J6).
- Calibrate button issues `CALIBRATE` twice, then `Y`, with delays.
- Keyboard deadman changed to `SHIFT` (left/right) to avoid UI button activation by `SPACE`.

---

## Recommendations

- Use Monitor mode initially with conservative speeds to confirm directionality and safety.
- For smoother control, use the V+ jog server on `SERIAL(2)` with 115200 baud (after loading the program).
- If you later need IO/state without ROS, add a minimal V+ status/IO server to complement the jog server.
- Retain small DMOVE steps (±5 clamp per cycle) and 20–50 Hz update rates for safety.

---

## References (from repo)

- V+ SCARA server: `adept_driver/V+/adept_ros_scara.v2` (ports 11000/11001/11002; SCARA conversions).
- MoveIt configs: `adept_cobra_s600_moveit_config/config` (controllers.yaml, joint_limits.yaml, kinematics.yaml).
- Joint names: `adept_cobra_s600_support/config/joint_names_adept_cobra_s600.yaml`.
- URDF/Xacro: `adept_cobra_s600_support/urdf`.
- IO service: `adept_msgs/srv/AdeptIO.srv`.
