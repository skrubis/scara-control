#!/usr/bin/env python3
"""
Cobra Jogger v2 — Enhanced Python GUI with dual control modes for Adept Cobra 600

New Features in v2:
- Mode 1: Direct monitor streaming (original method)
- Mode 2: V+ jog server with CRC16 checksum validation
- Protocol statistics and error monitoring
- Improved PS4 controller support

Requirements:
pip install pyserial pygame

V+ Program Required for Mode 2:
Load vplus_jog_server.v to your controller and configure SERIAL(2) to 115200 baud
"""

import sys
import time
import math
import threading
import queue
import struct
from dataclasses import dataclass
from enum import Enum

try:
    import serial
    from serial.tools import list_ports
except Exception as e:
    print("pyserial is required. Install with: pip install pyserial")
    raise

try:
    import pygame
    pygame.init()
    pygame.joystick.init()
except Exception as e:
    print("pygame is required. Install with: pip install pygame")
    raise

import tkinter as tk
from tkinter import ttk, messagebox

# ---------- CRC16 Checksum ----------

def crc16_ccitt(data: bytes) -> int:
    """
    Calculate CRC-16-CCITT checksum.
    Polynomial: 0x1021, Initial: 0xFFFF
    """
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

# ---------- Control Modes ----------

class ControlMode(Enum):
    MONITOR_STREAM = "Monitor Streaming"  # Mode 1: Direct DMOVE commands
    JOG_SERVER = "V+ Jog Server"          # Mode 2: Velocity packets with checksum

# ---------- Serial client ----------

class VPlusSerial:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()

    def connect(self, port: str, baud: int = 9600, timeout: float = 0.2):
        self.close()
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=timeout,
        )
        # Tickle the prompt
        self.send_raw("\r")
        time.sleep(0.1)
        self.read_nonblocking()  # flush

    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def send_raw(self, s: str):
        """Send a raw string to serial (no newline added)."""
        if not self.is_open():
            return
        with self.lock:
            self.ser.write(s.encode("ascii", errors="ignore"))

    def send_bytes(self, data: bytes):
        """Send raw bytes to serial."""
        if not self.is_open():
            return
        with self.lock:
            self.ser.write(data)

    def send_cmd(self, s: str):
        """Send a line terminated with CR (V+ monitor friendly)."""
        self.send_raw(s + "\r")

    def read_nonblocking(self) -> str:
        if not self.is_open():
            return ""
        with self.lock:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
            except Exception:
                return ""
        return data.decode("ascii", errors="ignore")

# ---------- Gamepad ----------

@dataclass
class PadState:
    connected: bool = False
    deadman: bool = False
    x: float = 0.0     # left stick X (-1..1)
    y: float = 0.0     # left stick Y (-1..1) (forward/back)
    z: float = 0.0     # triggers mapped to -1..1
    theta: float = 0.0 # right stick X (-1..1)
    buttons: dict = None

class Gamepad(threading.Thread):
    def __init__(self, out_queue: queue.Queue, stop_event: threading.Event, poll_hz: float = 50.0):
        super().__init__(daemon=True)
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.poll_dt = 1.0 / poll_hz
        self.joy = None
        self._find_joystick()

    def _find_joystick(self):
        pygame.joystick.quit()
        pygame.joystick.init()
        n = pygame.joystick.get_count()
        if n > 0:
            self.joy = pygame.joystick.Joystick(0)
            self.joy.init()
        else:
            self.joy = None

    def run(self):
        while not self.stop_event.is_set():
            if self.joy is None or not self.joy.get_init():
                self._find_joystick()

            state = PadState(connected=self.joy is not None, buttons={})
            for event in pygame.event.get():
                pass  # drain

            if self.joy:
                try:
                    # Axes commonly: 0=LX, 1=LY, 2=LT, 3=RX, 4=RY, 5=RT (varies by driver)
                    def axis(i, default=0.0):
                        if i < self.joy.get_numaxes():
                            return float(self.joy.get_axis(i))
                        return default

                    lx = axis(0, 0.0)
                    ly = axis(1, 0.0)
                    rx = axis(3, 0.0)

                    # Triggers: normalize LT/RT to [-1..1] where + is up and - is down
                    lt = axis(2, -1.0)  # often -1 released, +1 fully pressed
                    rt = axis(5, -1.0)  # often -1 released, +1 fully pressed
                    # Map to single z in [-1..1]: rt up (+), lt down (-)
                    z = ((rt + 1.0) * 0.5) - ((lt + 1.0) * 0.5)

                    # Buttons
                    btns = {i: int(self.joy.get_button(i)) for i in range(self.joy.get_numbuttons())}
                    # Deadman: RB (5) or A (0) for Xbox, R1 (5) or X (0) for PS4
                    deadman = bool(btns.get(5, 0) or btns.get(0, 0))

                    state.x = lx
                    state.y = -ly  # invert so stick up = +Y forward
                    state.theta = rx
                    state.z = z
                    state.deadman = deadman
                    state.buttons = btns

                except Exception:
                    state = PadState(connected=False, buttons={})

            self.out_queue.put(state)
            time.sleep(self.poll_dt)

# ---------- Jog control loop (Mode 1: Monitor Streaming) ----------

class JogLoop(threading.Thread):
    def __init__(self, ser: VPlusSerial, pad_queue: queue.Queue, stop_event: threading.Event, get_speed_fn, status_fn, get_mode_fn):
        super().__init__(daemon=True)
        self.ser = ser
        self.pad_queue = pad_queue
        self.stop_event = stop_event
        self.get_speed = get_speed_fn  # returns (mm_s, z_mm_s, deg_s)
        self.status = status_fn
        self.get_mode = get_mode_fn
        self.latest_pad = PadState()
        self.deadband = 0.15
        self.dt = 0.05  # 20 Hz for Mode 1
        self.dt_mode2 = 0.02  # 50 Hz for Mode 2
        
        # Statistics
        self.packets_sent = 0
        self.last_packet_time = time.time()
        
        # Thread-safe speed cache (updated from main thread)
        self.cached_speeds = (200.0, 100.0, 30.0)  # (xy, z, theta)
        self.speed_lock = threading.Lock()

    def run(self):
        t_last_flush = time.time()
        while not self.stop_event.is_set():
            # Drain to latest
            try:
                while True:
                    self.latest_pad = self.pad_queue.get_nowait()
            except queue.Empty:
                pass

            pad = self.latest_pad
            # Read cached speeds (thread-safe)
            with self.speed_lock:
                mm_s, z_mm_s, deg_s = self.cached_speeds
            mode = self.get_mode()

            if pad.connected and pad.deadman and self.ser.is_open():
                # Apply deadband
                x = pad.x if abs(pad.x) >= self.deadband else 0.0
                y = pad.y if abs(pad.y) >= self.deadband else 0.0
                z = pad.z if abs(pad.z) >= self.deadband else 0.0
                th = pad.theta if abs(pad.theta) >= self.deadband else 0.0

                if mode == ControlMode.MONITOR_STREAM:
                    # Mode 1: Send DMOVE commands
                    dt = self.dt
                    dx = x * mm_s * dt
                    dy = y * mm_s * dt
                    dz = z * z_mm_s * dt
                    dth = th * deg_s * dt

                    # Clip to sane small steps
                    dx = max(-5.0, min(5.0, dx))
                    dy = max(-5.0, min(5.0, dy))
                    dz = max(-5.0, min(5.0, dz))
                    dth = max(-5.0, min(5.0, dth))

                    cmd = f"EXECUTE DMOVE({dx:.3f},{dy:.3f},{dz:.3f},{dth:.3f})"
                    self.ser.send_cmd(cmd)
                    self.packets_sent += 1

                    # Rate-limit by reading/clearing echoed bytes
                    now = time.time()
                    if now - t_last_flush > 0.25:
                        _ = self.ser.read_nonblocking()
                        t_last_flush = now
                    
                    time.sleep(dt)

                elif mode == ControlMode.JOG_SERVER:
                    # Mode 2: Send velocity packet with checksum
                    dt = self.dt_mode2
                    vx = x * mm_s
                    vy = y * mm_s
                    vz = z * z_mm_s
                    vtheta = th * deg_s

                    # Build packet: V vx vy vz vtheta *CRC\r\n
                    data_str = f"V {vx:.2f} {vy:.2f} {vz:.2f} {vtheta:.2f} "
                    data_bytes = data_str.encode('ascii')
                    
                    # Calculate CRC16
                    crc = crc16_ccitt(data_bytes)
                    
                    # Complete packet
                    packet = f"{data_str}*{crc:04X}\r\n"
                    self.ser.send_raw(packet)
                    self.packets_sent += 1
                    self.last_packet_time = time.time()
                    
                    time.sleep(dt)
            else:
                # No motion - send zero velocities in Mode 2 to maintain connection
                if mode == ControlMode.JOG_SERVER and self.ser.is_open():
                    # Send zero packet periodically
                    if time.time() - self.last_packet_time > 0.1:
                        data_str = "V 0.00 0.00 0.00 0.00 "
                        data_bytes = data_str.encode('ascii')
                        crc = crc16_ccitt(data_bytes)
                        packet = f"{data_str}*{crc:04X}\r\n"
                        self.ser.send_raw(packet)
                        self.last_packet_time = time.time()
                
                time.sleep(0.05)

# ---------- GUI ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cobra Jogger v2")
        self.geometry("600x500")
        self.resizable(False, False)

        self.ser = VPlusSerial()
        self.pad_q = queue.Queue()
        self.stop_event = threading.Event()
        self.current_mode = ControlMode.MONITOR_STREAM

        # Top: Port controls
        frm = ttk.LabelFrame(self, text="Connection")
        frm.pack(fill="x", padx=10, pady=8)

        ttk.Label(frm, text="Port:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.cbo_port = ttk.Combobox(frm, values=self._list_ports(), width=20, state="readonly")
        self.cbo_port.grid(row=0, column=1, padx=6, pady=6)
        if self.cbo_port["values"]:
            self.cbo_port.current(0)

        ttk.Label(frm, text="Baud:").grid(row=0, column=2, padx=6, pady=6)
        self.cbo_baud = ttk.Combobox(frm, values=["9600","19200","38400","57600","115200"], width=8, state="readonly")
        self.cbo_baud.grid(row=0, column=3, padx=6, pady=6)
        self.cbo_baud.set("9600")

        self.btn_refresh = ttk.Button(frm, text="Refresh", command=self._refresh_ports)
        self.btn_refresh.grid(row=0, column=4, padx=6, pady=6)

        self.btn_connect = ttk.Button(frm, text="Connect", command=self.on_connect)
        self.btn_connect.grid(row=0, column=5, padx=6, pady=6)

        # Mode selection
        mfrm = ttk.LabelFrame(self, text="Control Mode")
        mfrm.pack(fill="x", padx=10, pady=8)

        ttk.Label(mfrm, text="Mode:").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.cbo_mode = ttk.Combobox(mfrm, values=[m.value for m in ControlMode], width=25, state="readonly")
        self.cbo_mode.grid(row=0, column=1, padx=6, pady=6)
        self.cbo_mode.set(ControlMode.MONITOR_STREAM.value)
        self.cbo_mode.bind("<<ComboboxSelected>>", self.on_mode_change)

        self.lbl_mode_info = ttk.Label(mfrm, text="Direct monitor commands (simple, works immediately)", foreground="blue")
        self.lbl_mode_info.grid(row=1, column=0, columnspan=2, padx=6, pady=2, sticky="w")

        # Power/cal
        pfrm = ttk.LabelFrame(self, text="Robot Control")
        pfrm.pack(fill="x", padx=10, pady=8)

        self.btn_enable = ttk.Button(pfrm, text="ENABLE POWER", command=lambda: self._send_line("ENABLE POWER"))
        self.btn_disable = ttk.Button(pfrm, text="DISABLE POWER", command=lambda: self._send_line("DISABLE POWER"))
        self.btn_cal = ttk.Button(pfrm, text="CALIBRATE", command=lambda: self._send_line("CALIBRATE"))
        self.btn_enable.grid(row=0, column=0, padx=6, pady=6)
        self.btn_disable.grid(row=0, column=1, padx=6, pady=6)
        self.btn_cal.grid(row=0, column=2, padx=6, pady=6)

        # Speed sliders
        sfrm = ttk.LabelFrame(self, text="Jog Speeds")
        sfrm.pack(fill="x", padx=10, pady=8)

        self.scale_xy = tk.DoubleVar(value=200.0)  # mm/s
        self.scale_z = tk.DoubleVar(value=100.0)   # mm/s
        self.scale_th = tk.DoubleVar(value=30.0)   # deg/s

        self._make_slider(sfrm, "XY (mm/s)", self.scale_xy, 10, 600, 0)
        self._make_slider(sfrm, "Z (mm/s)",  self.scale_z,  5, 300, 1)
        self._make_slider(sfrm, "Theta (deg/s)", self.scale_th, 5, 90, 2)

        # Status
        self.lbl_status = ttk.Label(self, text="Disconnected. Select mode and connect.", anchor="w")
        self.lbl_status.pack(fill="x", padx=12, pady=4)

        self.lbl_pad = ttk.Label(self, text="Gamepad: not connected", anchor="w")
        self.lbl_pad.pack(fill="x", padx=12, pady=2)

        self.lbl_stats = ttk.Label(self, text="Stats: 0 packets sent", anchor="w")
        self.lbl_stats.pack(fill="x", padx=12, pady=2)

        # Threads
        self.pad_thread = Gamepad(self.pad_q, self.stop_event, poll_hz=50.0)
        self.pad_thread.start()
        self.jog_thread = JogLoop(self.ser, self.pad_q, self.stop_event, self._get_speeds, self._set_status, self._get_mode)
        self.jog_thread.start()

        # Periodic UI updater
        self.after(100, self._tick_ui)

        # Close handling
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Help text
        self._show_tip()

    def _show_tip(self):
        tip = (
            "Cobra Jogger v2 - Dual Mode Control\n\n"
            "Mode 1: Monitor Streaming (default)\n"
            "- Simple, works immediately\n"
            "- ~20 Hz update rate\n\n"
            "Mode 2: V+ Jog Server (advanced)\n"
            "- Requires vplus_jog_server.v loaded on controller\n"
            "- Higher performance, 50 Hz updates\n"
            "- CRC16 checksum validation\n"
            "- Use SERIAL(2) at 115200 baud\n\n"
            "Controls: RB/R1 or A/X = deadman\n"
            "Left stick = XY, Triggers = Z, Right stick X = Theta\n"
            "Y/Triangle = enable, X/Square = calibrate, B/Circle = disable"
        )
        messagebox.showinfo("Cobra Jogger v2", tip)

    def _list_ports(self):
        try:
            return [p.device for p in list_ports.comports()]
        except Exception:
            return []

    def _refresh_ports(self):
        self.cbo_port["values"] = self._list_ports()
        if self.cbo_port["values"]:
            self.cbo_port.current(0)

    def _make_slider(self, parent, label, var, mn, mx, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        s = ttk.Scale(parent, from_=mn, to=mx, orient="horizontal", variable=var)
        s.grid(row=row, column=1, sticky="we", padx=6, pady=4)
        parent.grid_columnconfigure(1, weight=1)
        ent = ttk.Entry(parent, width=6, textvariable=var)
        ent.grid(row=row, column=2, padx=6, pady=4)

    def _get_speeds(self):
        return float(self.scale_xy.get()), float(self.scale_z.get()), float(self.scale_th.get())

    def _get_mode(self):
        return self.current_mode

    def _set_status(self, text):
        self.lbl_status.config(text=text)

    def _send_line(self, s: str):
        if not self.ser.is_open():
            messagebox.showwarning("Not connected", "Connect to serial first.")
            return
        if self.current_mode == ControlMode.JOG_SERVER:
            messagebox.showinfo("Mode Note", "In V+ Jog Server mode, use controller commands directly.\nSwitch to Monitor mode for manual commands.")
            return
        self.ser.send_cmd(s)

    def on_mode_change(self, event=None):
        mode_str = self.cbo_mode.get()
        for m in ControlMode:
            if m.value == mode_str:
                self.current_mode = m
                break
        
        # Update info label
        if self.current_mode == ControlMode.MONITOR_STREAM:
            self.lbl_mode_info.config(text="Direct monitor commands (simple, works immediately)")
            self.cbo_baud.set("9600")
        else:
            self.lbl_mode_info.config(text="V+ jog server mode (requires vplus_jog_server.v on controller, SERIAL(2) @ 115200)")
            self.cbo_baud.set("115200")

    def on_connect(self):
        if self.ser.is_open():
            self.ser.close()
            self.btn_connect.config(text="Connect")
            self._set_status("Disconnected.")
            return
        port = self.cbo_port.get()
        if not port:
            messagebox.showwarning("Port required", "Choose a serial port.")
            return
        try:
            baud = int(self.cbo_baud.get())
        except Exception:
            baud = 9600
        try:
            self.ser.connect(port, baud=baud, timeout=0.2)
            self.btn_connect.config(text="Disconnect")
            mode_name = self.current_mode.value
            self._set_status(f"Connected to {port} @ {baud} baud - Mode: {mode_name}")
        except Exception as e:
            messagebox.showerror("Serial error", str(e))

    def on_close(self):
        self.stop_event.set()
        try:
            self.pad_thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.jog_thread.join(timeout=0.5)
        except Exception:
            pass
        try:
            self.ser.close()
        except Exception:
            pass
        self.destroy()

    def _tick_ui(self):
        # Update cached speeds in jog thread (thread-safe)
        speeds = self._get_speeds()
        with self.jog_thread.speed_lock:
            self.jog_thread.cached_speeds = speeds
        
        # Update pad status and handle gamepad button-triggered robot actions
        try:
            pad = None
            while True:
                pad = self.pad_q.get_nowait()
        except queue.Empty:
            pass

        if pad is not None:
            if pad.connected:
                dead = "YES" if pad.deadman else "no"
                self.lbl_pad.config(text=f"Gamepad connected — deadman: {dead} | x={pad.x:+.2f} y={pad.y:+.2f} z={pad.z:+.2f} θ={pad.theta:+.2f}")
                # Buttons: Y (3) enable, X (2) calibrate, B (1) disable (Xbox/PS4 mapping)
                if pad.buttons and self.current_mode == ControlMode.MONITOR_STREAM:
                    if pad.buttons.get(3, 0):  # Y/Triangle
                        self._send_line("ENABLE POWER")
                    if pad.buttons.get(2, 0):  # X/Square
                        self._send_line("CALIBRATE")
                    if pad.buttons.get(1, 0):  # B/Circle
                        self._send_line("DISABLE POWER")
            else:
                self.lbl_pad.config(text="Gamepad: not connected")

        # Update statistics
        if self.ser.is_open():
            packets = self.jog_thread.packets_sent
            mode_name = self.current_mode.value
            self.lbl_stats.config(text=f"Stats: {packets} packets sent | Mode: {mode_name}")
            # Drain serial echo intermittently
            _ = self.ser.read_nonblocking()

        self.after(100, self._tick_ui)

if __name__ == "__main__":
    app = App()
    app.mainloop()
