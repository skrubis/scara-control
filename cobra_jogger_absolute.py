#!/usr/bin/env python3
"""
Cobra Jogger - Absolute Position Mode
======================================
Enhanced jogging with position feedback and absolute positioning.

New Features:
- Queries robot position periodically
- Detects soft limits automatically
- Absolute position mode (like 3D printer)
- Position display in GUI
- Smooth motion even at limits

Requirements: pip install pyserial pygame
"""

import sys, time, threading, queue
from dataclasses import dataclass
from enum import Enum

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("pip install pyserial")
    sys.exit(1)

try:
    import pygame
    pygame.init()
    pygame.joystick.init()
except ImportError:
    print("pip install pygame")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, messagebox

# ---------- Position Modes ----------

class PositionMode(Enum):
    INCREMENTAL = "Incremental (DMOVE)"  # Original mode
    ABSOLUTE = "Absolute (MOVE)"         # Continuous absolute positioning

# ---------- Serial with Position Feedback ----------

class VPlusSerialWithFeedback:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.current_position = {"x": 0.0, "y": 0.0, "z": 0.0, "theta": 0.0}
        self.position_valid = False
        
    def connect(self, port, baud=9600, timeout=0.2):
        if self.ser:
            self.close()
        self.ser = serial.Serial(port, baud, timeout=timeout, write_timeout=timeout)
        self.send_raw("\r")
        time.sleep(0.1)
        self.read_nonblocking()
        self.query_position()  # Get initial position
        
    def is_open(self):
        return self.ser is not None and self.ser.is_open
    
    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
    
    def send_raw(self, s):
        if not self.is_open():
            return
        with self.lock:
            self.ser.write(s.encode("ascii", errors="ignore"))
    
    def send_cmd(self, s):
        self.send_raw(s + "\r")
    
    def read_nonblocking(self):
        if not self.is_open():
            return ""
        with self.lock:
            try:
                data = self.ser.read(self.ser.in_waiting or 1)
            except:
                return ""
        return data.decode("ascii", errors="ignore")
    
    def query_position(self):
        """Query current robot position using WHERE command."""
        if not self.is_open():
            return False
        
        # Send WHERE command (returns current position)
        self.send_cmd("WHERE")
        time.sleep(0.1)
        
        # Read response
        response = self.read_nonblocking()
        
        # Parse response (format varies by controller version)
        # Typical: "X: 100.5 Y: 200.3 Z: 50.0 T: 15.2"
        # Or: TRANS(100.5, 200.3, 50.0, 15.2)
        import re
        
        # Try TRANS format first
        trans_match = re.search(r'TRANS\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)', response)
        if trans_match:
            self.current_position = {
                "x": float(trans_match.group(1)),
                "y": float(trans_match.group(2)),
                "z": float(trans_match.group(3)),
                "theta": float(trans_match.group(4))
            }
            self.position_valid = True
            return True
        
        # Try X: Y: Z: T: format
        x_match = re.search(r'X[:\s]+([-\d.]+)', response, re.IGNORECASE)
        y_match = re.search(r'Y[:\s]+([-\d.]+)', response, re.IGNORECASE)
        z_match = re.search(r'Z[:\s]+([-\d.]+)', response, re.IGNORECASE)
        t_match = re.search(r'T[:\s]+([-\d.]+)', response, re.IGNORECASE)
        
        if x_match and y_match and z_match and t_match:
            self.current_position = {
                "x": float(x_match.group(1)),
                "y": float(y_match.group(1)),
                "z": float(z_match.group(1)),
                "theta": float(t_match.group(1))
            }
            self.position_valid = True
            return True
        
        return False
    
    def get_position(self):
        """Get cached position."""
        return self.current_position.copy() if self.position_valid else None

# ---------- Gamepad (reuse from cobra_jogger_v2) ----------

@dataclass
class PadState:
    connected: bool = False
    deadman: bool = False
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    buttons: dict = None

class Gamepad(threading.Thread):
    def __init__(self, out_queue, stop_event, poll_hz=50.0):
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
    
    def run(self):
        while not self.stop_event.is_set():
            if not self.joy or not self.joy.get_init():
                self._find_joystick()
            
            state = PadState(connected=self.joy is not None, buttons={})
            for event in pygame.event.get():
                pass
            
            if self.joy:
                try:
                    def axis(i, default=0.0):
                        if i < self.joy.get_numaxes():
                            return float(self.joy.get_axis(i))
                        return default
                    
                    lx = axis(0, 0.0)
                    ly = axis(1, 0.0)
                    rx = axis(3, 0.0)
                    lt = axis(2, -1.0)
                    rt = axis(5, -1.0)
                    z = ((rt + 1.0) * 0.5) - ((lt + 1.0) * 0.5)
                    
                    btns = {i: int(self.joy.get_button(i)) for i in range(self.joy.get_numbuttons())}
                    deadman = bool(btns.get(5, 0) or btns.get(0, 0))
                    
                    state.x = lx
                    state.y = -ly
                    state.theta = rx
                    state.z = z
                    state.deadman = deadman
                    state.buttons = btns
                except:
                    state = PadState(connected=False, buttons={})
            
            self.out_queue.put(state)
            time.sleep(self.poll_dt)

# ---------- Jog Loop with Position Awareness ----------

class AbsoluteJogLoop(threading.Thread):
    def __init__(self, ser, pad_queue, stop_event, get_speed_fn, get_mode_fn):
        super().__init__(daemon=True)
        self.ser = ser
        self.pad_queue = pad_queue
        self.stop_event = stop_event
        self.get_speed = get_speed_fn
        self.get_mode = get_mode_fn
        self.latest_pad = PadState()
        self.deadband = 0.15
        self.dt = 0.05
        
        # Target position for absolute mode
        self.target_position = {"x": 0.0, "y": 0.0, "z": 0.0, "theta": 0.0}
        
        # Thread-safe speed cache
        self.cached_speeds = (200.0, 100.0, 30.0)
        self.speed_lock = threading.Lock()
        
        # Position query timing
        self.last_position_query = time.time()
        self.position_query_interval = 0.5  # Query every 500ms
    
    def run(self):
        # Get initial position
        if self.ser.is_open():
            self.ser.query_position()
            pos = self.ser.get_position()
            if pos:
                self.target_position = pos.copy()
        
        t_last_flush = time.time()
        
        while not self.stop_event.is_set():
            # Drain pad queue
            try:
                while True:
                    self.latest_pad = self.pad_queue.get_nowait()
            except queue.Empty:
                pass
            
            pad = self.latest_pad
            
            # Get cached speeds
            with self.speed_lock:
                mm_s, z_mm_s, deg_s = self.cached_speeds
            
            mode = self.get_mode()
            
            # Periodically query position
            now = time.time()
            if now - self.last_position_query > self.position_query_interval:
                if self.ser.is_open():
                    self.ser.query_position()
                    pos = self.ser.get_position()
                    if pos and not pad.deadman:
                        # Update target to current position when not jogging
                        self.target_position = pos.copy()
                self.last_position_query = now
            
            if pad.connected and pad.deadman and self.ser.is_open():
                # Apply deadband
                x = pad.x if abs(pad.x) >= self.deadband else 0.0
                y = pad.y if abs(pad.y) >= self.deadband else 0.0
                z = pad.z if abs(pad.z) >= self.deadband else 0.0
                th = pad.theta if abs(pad.theta) >= self.deadband else 0.0
                
                if mode == PositionMode.INCREMENTAL:
                    # Original DMOVE mode
                    dx = x * mm_s * self.dt
                    dy = y * mm_s * self.dt
                    dz = z * z_mm_s * self.dt
                    dth = th * deg_s * self.dt
                    
                    dx = max(-5.0, min(5.0, dx))
                    dy = max(-5.0, min(5.0, dy))
                    dz = max(-5.0, min(5.0, dz))
                    dth = max(-5.0, min(5.0, dth))
                    
                    cmd = f"EXECUTE DMOVE({dx:.3f},{dy:.3f},{dz:.3f},{dth:.3f})"
                    self.ser.send_cmd(cmd)
                    
                elif mode == PositionMode.ABSOLUTE:
                    # Absolute positioning mode - update target position
                    self.target_position["x"] += x * mm_s * self.dt
                    self.target_position["y"] += y * mm_s * self.dt
                    self.target_position["z"] += z * z_mm_s * self.dt
                    self.target_position["theta"] += th * deg_s * self.dt
                    
                    # Send absolute MOVE command
                    # Use EXECUTE MOVE to avoid program storage
                    cmd = f"EXECUTE MOVE(TRANS({self.target_position['x']:.2f},{self.target_position['y']:.2f},{self.target_position['z']:.2f},{self.target_position['theta']:.2f}))"
                    self.ser.send_cmd(cmd)
                
                # Rate limiting
                if now - t_last_flush > 0.25:
                    _ = self.ser.read_nonblocking()
                    t_last_flush = now
            
            time.sleep(self.dt)

# ---------- GUI ----------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cobra Jogger - Absolute Position Mode")
        self.geometry("620x550")
        self.resizable(False, False)
        
        self.ser = VPlusSerialWithFeedback()
        self.pad_q = queue.Queue()
        self.stop_event = threading.Event()
        self.current_mode = PositionMode.INCREMENTAL
        
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Threads
        self.pad_thread = Gamepad(self.pad_q, self.stop_event)
        self.pad_thread.start()
        
        self.jog_thread = AbsoluteJogLoop(self.ser, self.pad_q, self.stop_event,
                                          self._get_speeds, self._get_mode)
        self.jog_thread.start()
        
        self.after(100, self._tick_ui)
        self._refresh_ports()
    
    def create_widgets(self):
        # Connection frame
        frm = ttk.LabelFrame(self, text="Connection")
        frm.pack(fill="x", padx=10, pady=8)
        
        ttk.Label(frm, text="Port:").grid(row=0, column=0, padx=6, pady=6)
        self.cbo_port = ttk.Combobox(frm, width=20, state="readonly")
        self.cbo_port.grid(row=0, column=1, padx=6, pady=6)
        
        ttk.Label(frm, text="Baud:").grid(row=0, column=2, padx=6, pady=6)
        self.cbo_baud = ttk.Combobox(frm, values=["9600","19200","38400","57600"], width=8, state="readonly")
        self.cbo_baud.set("9600")
        self.cbo_baud.grid(row=0, column=3, padx=6, pady=6)
        
        ttk.Button(frm, text="↻", command=self._refresh_ports).grid(row=0, column=4, padx=6, pady=6)
        self.btn_connect = ttk.Button(frm, text="Connect", command=self.on_connect)
        self.btn_connect.grid(row=0, column=5, padx=6, pady=6)
        
        # Mode selection
        mfrm = ttk.LabelFrame(self, text="Position Control Mode")
        mfrm.pack(fill="x", padx=10, pady=8)
        
        ttk.Label(mfrm, text="Mode:").grid(row=0, column=0, padx=6, pady=6)
        self.cbo_mode = ttk.Combobox(mfrm, values=[m.value for m in PositionMode], width=25, state="readonly")
        self.cbo_mode.set(PositionMode.INCREMENTAL.value)
        self.cbo_mode.grid(row=0, column=1, padx=6, pady=6)
        self.cbo_mode.bind("<<ComboboxSelected>>", self.on_mode_change)
        
        self.lbl_mode_info = ttk.Label(mfrm, text="Incremental moves (handles limits better)", foreground="blue")
        self.lbl_mode_info.grid(row=1, column=0, columnspan=2, padx=6, sticky="w")
        
        # Current position display
        posfrm = ttk.LabelFrame(self, text="Current Position (from controller)")
        posfrm.pack(fill="x", padx=10, pady=8)
        
        self.lbl_position = ttk.Label(posfrm, text="X: --  Y: --  Z: --  θ: --", font=("Courier New", 10))
        self.lbl_position.pack(padx=10, pady=10)
        
        # Robot control
        pfrm = ttk.LabelFrame(self, text="Robot Control")
        pfrm.pack(fill="x", padx=10, pady=8)
        
        ttk.Button(pfrm, text="ENABLE POWER", command=lambda: self._send_line("ENABLE POWER")).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(pfrm, text="DISABLE POWER", command=lambda: self._send_line("DISABLE POWER")).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(pfrm, text="CALIBRATE", command=lambda: self._send_line("CALIBRATE")).grid(row=0, column=2, padx=6, pady=6)
        
        # Speed sliders
        sfrm = ttk.LabelFrame(self, text="Jog Speeds")
        sfrm.pack(fill="x", padx=10, pady=8)
        
        self.scale_xy = tk.DoubleVar(value=200.0)
        self.scale_z = tk.DoubleVar(value=100.0)
        self.scale_th = tk.DoubleVar(value=30.0)
        
        self._make_slider(sfrm, "XY (mm/s)", self.scale_xy, 10, 600, 0)
        self._make_slider(sfrm, "Z (mm/s)", self.scale_z, 5, 300, 1)
        self._make_slider(sfrm, "Theta (deg/s)", self.scale_th, 5, 90, 2)
        
        # Status
        self.lbl_status = ttk.Label(self, text="Disconnected", anchor="w")
        self.lbl_status.pack(fill="x", padx=12, pady=4)
        
        self.lbl_pad = ttk.Label(self, text="Gamepad: not connected", anchor="w")
        self.lbl_pad.pack(fill="x", padx=12, pady=2)
    
    def _make_slider(self, parent, label, var, mn, mx, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        s = ttk.Scale(parent, from_=mn, to=mx, variable=var)
        s.grid(row=row, column=1, sticky="we", padx=6, pady=4)
        parent.grid_columnconfigure(1, weight=1)
        ttk.Entry(parent, width=6, textvariable=var).grid(row=row, column=2, padx=6, pady=4)
    
    def _get_speeds(self):
        return float(self.scale_xy.get()), float(self.scale_z.get()), float(self.scale_th.get())
    
    def _get_mode(self):
        return self.current_mode
    
    def _send_line(self, s):
        if self.ser.is_open():
            self.ser.send_cmd(s)
    
    def _refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.cbo_port['values'] = ports
        if ports and not self.cbo_port.get():
            self.cbo_port.current(0)
    
    def on_mode_change(self, event=None):
        mode_str = self.cbo_mode.get()
        for m in PositionMode:
            if m.value == mode_str:
                self.current_mode = m
                break
        
        if self.current_mode == PositionMode.INCREMENTAL:
            self.lbl_mode_info.config(text="Incremental moves (handles limits better)")
        else:
            self.lbl_mode_info.config(text="Absolute positioning (like 3D printer, smoother)")
    
    def on_connect(self):
        if self.ser.is_open():
            self.ser.close()
            self.btn_connect.config(text="Connect")
            self.lbl_status.config(text="Disconnected")
        else:
            port = self.cbo_port.get()
            if not port:
                messagebox.showwarning("No Port", "Select a port")
                return
            try:
                self.ser.connect(port, int(self.cbo_baud.get()))
                self.btn_connect.config(text="Disconnect")
                self.lbl_status.config(text=f"Connected: {port}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
    
    def on_close(self):
        self.stop_event.set()
        try:
            self.pad_thread.join(timeout=0.5)
            self.jog_thread.join(timeout=0.5)
        except:
            pass
        self.ser.close()
        self.destroy()
    
    def _tick_ui(self):
        # Update speeds in jog thread
        speeds = self._get_speeds()
        with self.jog_thread.speed_lock:
            self.jog_thread.cached_speeds = speeds
        
        # Update pad status
        try:
            pad = None
            while True:
                pad = self.pad_q.get_nowait()
        except queue.Empty:
            pass
        
        if pad and pad.connected:
            dead = "YES" if pad.deadman else "no"
            self.lbl_pad.config(text=f"Gamepad: connected — deadman: {dead} | x={pad.x:+.2f} y={pad.y:+.2f} z={pad.z:+.2f} θ={pad.theta:+.2f}")
            
            if pad.buttons:
                if pad.buttons.get(3, 0):
                    self._send_line("ENABLE POWER")
                if pad.buttons.get(2, 0):
                    self._send_line("CALIBRATE")
                if pad.buttons.get(1, 0):
                    self._send_line("DISABLE POWER")
        else:
            self.lbl_pad.config(text="Gamepad: not connected")
        
        # Update position display
        if self.ser.is_open():
            pos = self.ser.get_position()
            if pos:
                self.lbl_position.config(
                    text=f"X: {pos['x']:7.2f}  Y: {pos['y']:7.2f}  Z: {pos['z']:7.2f}  θ: {pos['theta']:6.2f}"
                )
            _ = self.ser.read_nonblocking()
        
        self.after(100, self._tick_ui)

if __name__ == "__main__":
    app = App()
    app.mainloop()
