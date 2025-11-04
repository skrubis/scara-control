#!/usr/bin/env python3
import sys
import time
import re
import threading
import queue
from dataclasses import dataclass
from enum import Enum

try:
    import serial
    from serial.tools import list_ports
except Exception:
    print("pyserial is required. Install with: pip install pyserial")
    sys.exit(1)

try:
    import pygame
    pygame.init()
    pygame.joystick.init()
except Exception:
    print("pygame is required. Install with: pip install pygame")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter import scrolledtext
from math import sqrt, copysign, atan2, cos, sin, pi

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc

class Envelope:
    RMIN = 180.0
    RMAX = 560.0
    BACK_W2 = 150.0
    ZMIN = 185.0
    ZMAX = 380.0
    ANG_MAX_DEG = 100.0  # keep within +/- this angle around +X

def clamp_abs(x, y, z, r, E=Envelope):
    clamped = False
    # Z window
    z0 = z
    z = max(E.ZMIN, min(E.ZMAX, z)); clamped |= (z != z0)
    # rear exclusion band (when behind mast)
    if x < 0 and abs(y) < E.BACK_W2:
        y = copysign(E.BACK_W2, y if y != 0 else 1.0); clamped = True
    # radial donut (scale along ray) and angular wedge clamp
    rad2 = x*x + y*y
    if rad2 > 1e-9:
        rad = sqrt(rad2)
        if rad < E.RMIN:
            s = E.RMIN/rad; x, y = x*s, y*s; clamped = True
            rad = E.RMIN
        elif rad > E.RMAX:
            s = E.RMAX/rad; x, y = x*s, y*s; clamped = True
            rad = E.RMAX
        # angular limit (about +X)
        ang = atan2(y, x)
        ang_max = (E.ANG_MAX_DEG * pi / 180.0)
        if abs(ang) > ang_max:
            ang = copysign(ang_max, ang)
            x, y = rad * cos(ang), rad * sin(ang)
            clamped = True
    return x, y, z, r, clamped

def clamp_rel_from_feedback(last_fb, dx, dy, dz, dr, E=Envelope):
    x0, y0, z0, r0 = last_fb
    return clamp_abs(x0+dx, y0+dy, z0+dz, r0+dr, E)

class ScaraJogPad(tk.Frame):
    def __init__(self, master, send_abs_cb, get_r_cb=lambda: 0.0, width=360, height=360, **kw):
        super().__init__(master, **kw)
        self.send_abs_cb = send_abs_cb
        self.get_r_cb = get_r_cb
        self.canvas = tk.Canvas(self, width=width, height=height, bg="#111", highlightthickness=1, highlightbackground="#555")
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(4,6), pady=4)
        self.zscale = tk.Scale(self, from_=Envelope.ZMAX, to=Envelope.ZMIN, orient="vertical", length=height-8)
        self.zscale.set((Envelope.ZMIN+Envelope.ZMAX)/2)
        self.zscale.grid(row=0, column=1, sticky="ns", padx=(0,6), pady=4)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        pad = 10
        self.cx = width//2
        self.cy = height//2
        self.scale = (min(width, height)/2 - pad) / Envelope.RMAX
        self.fb = None
        self.target = None
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<B1-Motion>", self._click)
        self._draw_static()
        self._redraw()

    def _draw_static(self):
        c = self.canvas; s = self.scale; cx, cy = self.cx, self.cy
        c.delete("static")
        R = Envelope.RMAX * s
        c.create_oval(cx-R, cy-R, cx+R, cy+R, outline="#444", width=2, tags="static")
        r = Envelope.RMIN * s
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#444", width=2, tags="static")
        yb = Envelope.BACK_W2 * s
        c.create_rectangle(cx-R, cy-yb, cx, cy+yb, fill="#882222", outline="", tags="static")
        # wedge boundary lines (+/- ANG_MAX_DEG)
        ang = Envelope.ANG_MAX_DEG * pi / 180.0
        wx = Envelope.RMAX * cos(ang); wy = Envelope.RMAX * sin(ang)
        p_pos = self._w2c(wx, wy)
        p_neg = self._w2c(wx, -wy)
        c.create_line(cx, cy, p_pos[0], p_pos[1], fill="#555", dash=(4,3), tags="static")
        c.create_line(cx, cy, p_neg[0], p_neg[1], fill="#555", dash=(4,3), tags="static")
        c.create_oval(cx-18, cy-18, cx+18, cy+18, fill="#888", outline="", tags="static")
        c.create_line(cx, cy, cx+35, cy, fill="#666", width=2, tags="static")
        c.create_line(cx, cy, cx, cy-35, fill="#666", width=2, tags="static")

    def _redraw(self):
        c = self.canvas
        c.delete("dyn")
        if self.fb:
            x, y, _z, _r = self.fb
            self._draw_arm(x, y, fill="#8fd", tags="dyn")
        if self.target:
            x, y, _z, _r = self.target
            px, py = self._w2c(x, y)
            c.create_oval(px-4, py-4, px+4, py+4, outline="#0f0", fill="", width=2, tags="dyn")

    def _draw_arm(self, x, y, fill="#9cf", tags=None):
        L1 = Envelope.RMAX * 0.5
        L2 = L1
        r2 = x*x + y*y
        if r2 < 1e-6:
            return
        c2 = (r2 - L1*L1 - L2*L2) / (2*L1*L2)
        c2 = max(-1.0, min(1.0, c2))
        s2 = sqrt(max(0.0, 1.0 - c2*c2))
        th2 = atan2(s2, c2)
        th1 = atan2(y, x) - atan2(L2*s2, L1 + L2*c2)
        x1 = L1 * cos(th1); y1 = L1 * sin(th1)
        x2 = x1 + L2 * cos(th1 + th2); y2 = y1 + L2 * sin(th1 + th2)
        p0 = self._w2c(0, 0); p1 = self._w2c(x1, y1); p2 = self._w2c(x2, y2)
        self.canvas.create_line(p0[0], p0[1], p1[0], p1[1], p2[0], p2[1], fill=fill, width=5, capstyle="round", tags=tags)

    def _click(self, ev):
        xw, yw = self._c2w(ev.x, ev.y)
        z = float(self.zscale.get())
        r = float(self.get_r_cb() or 0.0)
        xw, yw, z, r, _ = clamp_abs(xw, yw, z, r)
        self.target = (xw, yw, z, r)
        self._redraw()
        try:
            self.send_abs_cb(xw, yw, z, r)
        except Exception:
            pass

    def _w2c(self, x, y):
        return (self.cx + x*self.scale, self.cy - y*self.scale)

    def _c2w(self, px, py):
        return ((px - self.cx)/self.scale, -(py - self.cy)/self.scale)

    def set_feedback(self, x, y, z, r):
        self.fb = (x, y, z, r)
        self._redraw()

class SerialManager:
    def __init__(self):
        self.ser = None
        self.lock = threading.Lock()
        self.read_thread = None
        self.stop_event = threading.Event()
        self.response_queue = queue.Queue()
        self.monitor_callback = None
        self.crlf = True

    def ports(self):
        try:
            return [p.device for p in list_ports.comports()]
        except Exception:
            return []

    def connect(self, port: str, baud: int = 9600, timeout: float = 0.1):
        self.disconnect()
        # Enable software XON/XOFF and DSR/DTR as per legacy script defaults
        self.ser = serial.Serial(
            port=port,
            baudrate=baud,
            timeout=timeout,
            write_timeout=1.0,
            xonxoff=True,
            rtscts=False,
            dsrdtr=True,
        )
        time.sleep(0.2)
        try:
            self.ser.reset_input_buffer()
        except Exception:
            pass
        self.send_line("")
        time.sleep(0.05)
        self.stop_event.clear()
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

    def is_connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def disconnect(self):
        if self.read_thread:
            self.stop_event.set()
            try:
                self.read_thread.join(timeout=1.0)
            except Exception:
                pass
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.read_thread = None

    def send_raw(self, s: str):
        if not self.is_connected():
            return
        with self.lock:
            self.ser.write(s.encode("ascii", errors="ignore"))

    def send_line(self, text: str):
        if not self.is_connected():
            return
        with self.lock:
            eol = "\r\n" if self.crlf else "\r"
            self.ser.write((text + eol).encode("ascii", errors="ignore"))
        if self.monitor_callback:
            try:
                self.monitor_callback(f"> {text}")
            except Exception:
                pass

    def send_command(self, cmd: str, timeout: float = 2.0) -> str:
        if not self.is_connected():
            return ""
        try:
            while True:
                self.response_queue.get_nowait()
        except queue.Empty:
            pass
        self.send_line(cmd)
        lines = []
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self.response_queue.get(timeout=0.15)
            except queue.Empty:
                continue
            lines.append(line)
            if line.strip().endswith('.') or 'ERROR' in line.upper():
                break
        return "\n".join(lines)

    def _read_loop(self):
        buf = ""
        while not self.stop_event.is_set():
            try:
                if self.ser and self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    text = data.decode("ascii", errors="ignore")
                    buf += text
                    while "\n" in buf or "\r" in buf:
                        idxs = [i for i in [buf.find("\n"), buf.find("\r")] if i >= 0]
                        if not idxs:
                            break
                        i = min(idxs)
                        line = buf[:i]
                        buf = buf[i+1:]
                        if line:
                            self.response_queue.put(line)
                            if self.monitor_callback:
                                try:
                                    self.monitor_callback(line)
                                except Exception:
                                    pass
                time.sleep(0.01)
            except Exception:
                time.sleep(0.1)

@dataclass
class PadState:
    connected: bool = False
    deadman: bool = False
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    theta: float = 0.0
    buttons: dict = None


class ControlMode(Enum):
    MONITOR_STREAM = "Monitor Streaming"
    JOG_SERVER = "V+ Jog Server"
    ABSOLUTE = "Absolute (MOVE)"


class Gamepad(threading.Thread):
    def __init__(self, out_queue: queue.Queue, stop_event: threading.Event, poll_hz: float = 50.0):
        super().__init__(daemon=True)
        self.out_q = out_queue
        self.stop_event = stop_event
        self.dt = 1.0 / poll_hz
        self.joy = None
        self._find()

    def _find(self):
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
                self._find()
            st = PadState(connected=self.joy is not None, buttons={})
            for _ in pygame.event.get():
                pass
            if self.joy:
                try:
                    def axis(i, d=0.0):
                        return float(self.joy.get_axis(i)) if i < self.joy.get_numaxes() else d
                    lx = axis(0)
                    ly = axis(1)
                    rx = axis(3)
                    lt = axis(2, -1.0)
                    rt = axis(5, -1.0)
                    z = ((rt + 1.0)*0.5) - ((lt + 1.0)*0.5)
                    btns = {i: int(self.joy.get_button(i)) for i in range(self.joy.get_numbuttons())}
                    dead = bool(btns.get(5, 0) or btns.get(0, 0))
                    st.x = lx
                    st.y = -ly
                    st.theta = rx
                    st.z = z
                    st.deadman = dead
                    st.buttons = btns
                except Exception:
                    st = PadState(connected=False, buttons={})
            self.out_q.put(st)
            time.sleep(self.dt)


class JogLoop(threading.Thread):
    def __init__(self, serial_mgr: SerialManager, pad_q: queue.Queue, stop_event: threading.Event,
                 get_speeds, get_mode, get_keyboard_state, status_cb):
        super().__init__(daemon=True)
        self.ser = serial_mgr
        self.pad_q = pad_q
        self.stop_event = stop_event
        self.get_speeds = get_speeds
        self.get_mode = get_mode
        self.get_keyboard_state = get_keyboard_state
        self.status = status_cb
        self.latest_pad = PadState()
        self.deadband = 0.15
        self.dt_mode1 = 0.05
        self.dt_mode2 = 0.02
        self.dt_abs = 0.05
        self.target = dict(x=0.0, y=0.0, z=0.0, theta=0.0)
        self.last_packet_time = time.time()
        self.packets_sent = 0

    def _query_position(self) -> dict | None:
        if not self.ser.is_connected():
            return None
        resp = self.ser.send_command("WHERE", timeout=1.2)
        # Format 1: TRANS(x,y,z,theta)
        m = re.search(r'TRANS\s*\(\s*([\-\d.]+)\s*,\s*([\-\d.]+)\s*,\s*([\-\d.]+)\s*,\s*([\-\d.]+)', resp)
        if m:
            return dict(x=float(m.group(1)), y=float(m.group(2)), z=float(m.group(3)), theta=float(m.group(4)))
        # Format 2: Labeled X: Y: Z: T:
        mx = re.search(r'X[:\s]+([\-\d.]+)', resp, re.I)
        my = re.search(r'Y[:\s]+([\-\d.]+)', resp, re.I)
        mz = re.search(r'Z[:\s]+([\-\d.]+)', resp, re.I)
        mt = re.search(r'T[:\s]+([\-\d.]+)', resp, re.I)
        if mx and my and mz and mt:
            return dict(x=float(mx.group(1)), y=float(my.group(1)), z=float(mz.group(1)), theta=float(mt.group(1)))
        # Format 3: Two-line table with headers "X Y Z y p r Hand" then numbers, then J1..J6 line
        # Extract the first line of 6 floats (X,Y,Z,y,p,r)
        lines = [ln.strip() for ln in resp.splitlines() if ln.strip()]
        vals_xyzr = None
        for ln in lines:
            nums = re.findall(r'[-+]?\d+(?:\.\d+)?', ln)
            if len(nums) >= 6:
                # Heuristic: prefer the first occurrence with 6+ floats following a header line
                vals = list(map(float, nums[:6]))
                # Extra guard: look for preceding header keywords in the whole resp
                if re.search(r'\bX\b.*\bY\b.*\bZ\b.*\by\b.*\bp\b.*\br\b', resp):
                    vals_xyzr = vals  # [X, Y, Z, y, p, r]
                    break
        if vals_xyzr:
            x, y, z, _y_ang, _p_ang, r_ang = vals_xyzr
            return dict(x=float(x), y=float(y), z=float(z), theta=float(r_ang))
        # Fallback: parse J1..J6 numeric line and use J4 as theta if present
        for ln in lines:
            nums = re.findall(r'[-+]?\d+(?:\.\d+)?', ln)
            if len(nums) >= 4 and 'J1' in resp and 'J2' in resp:
                try:
                    j4 = float(nums[3])
                    # Without X/Y/Z here we cannot reliably infer; skip unless we also found X/Y/Z earlier
                except Exception:
                    pass
        return None

    def run(self):
        t_last_flush = time.time()
        last_pos_q = 0.0
        while not self.stop_event.is_set():
            # Drain to latest
            try:
                while True:
                    self.latest_pad = self.pad_q.get_nowait()
            except queue.Empty:
                pass

            kb = self.get_keyboard_state()
            pad = self.latest_pad

            x_in = pad.x if pad.connected else 0.0
            y_in = pad.y if pad.connected else 0.0
            z_in = pad.z if pad.connected else 0.0
            th_in = pad.theta if pad.connected else 0.0
            dead = pad.deadman if pad.connected else False

            # Keyboard overrides if stronger
            if abs(kb['x']) > abs(x_in):
                x_in = kb['x']
            if abs(kb['y']) > abs(y_in):
                y_in = kb['y']
            if abs(kb['z']) > abs(z_in):
                z_in = kb['z']
            if abs(kb['theta']) > abs(th_in):
                th_in = kb['theta']
            dead = kb['deadman'] or dead

            mm_s, z_mm_s, deg_s = self.get_speeds()
            mode = self.get_mode()

            if dead and self.ser.is_connected():
                def filt(v):
                    return v if abs(v) >= self.deadband else 0.0
                x = filt(x_in)
                y = filt(y_in)
                z = filt(z_in)
                th = filt(th_in)

                if mode == ControlMode.MONITOR_STREAM:
                    dt = self.dt_mode1
                    dx = max(-5.0, min(5.0, x * mm_s * dt))
                    dy = max(-5.0, min(5.0, y * mm_s * dt))
                    dz = max(-5.0, min(5.0, z * z_mm_s * dt))
                    dth = max(-5.0, min(5.0, th * deg_s * dt))
                    if dx != 0.0 or dy != 0.0 or dz != 0.0 or dth != 0.0:
                        cmd = f"DO DMOVE {dx:.3f},{dy:.3f},{dz:.3f},{dth:.3f}"
                        self.ser.send_line(cmd)
                        self.packets_sent += 1
                    time.sleep(dt)

                elif mode == ControlMode.JOG_SERVER:
                    dt = self.dt_mode2
                    vx = x * mm_s
                    vy = y * mm_s
                    vz = z * z_mm_s
                    vth = th * deg_s
                    data_str = f"V {vx:.2f} {vy:.2f} {vz:.2f} {vth:.2f} "
                    c = crc16_ccitt(data_str.encode('ascii'))
                    pkt = f"{data_str}*{c:04X}\r\n"
                    self.ser.send_raw(pkt)
                    self.packets_sent += 1
                    self.last_packet_time = time.time()
                    time.sleep(dt)

                elif mode == ControlMode.ABSOLUTE:
                    dt = self.dt_abs
                    if time.time() - last_pos_q > 0.5 or (self.target['x'] == 0.0 and self.target['y'] == 0.0 and self.target['z'] == 0.0 and self.target['theta'] == 0.0):
                        pos = self._query_position()
                        if pos:
                            self.target.update(pos)
                        last_pos_q = time.time()
                    # Use small incremental DMOVE steps; prefix with DO for monitor execution
                    dx = max(-5.0, min(5.0, x * mm_s * dt))
                    dy = max(-5.0, min(5.0, y * mm_s * dt))
                    dz = max(-5.0, min(5.0, z * z_mm_s * dt))
                    dth = max(-5.0, min(5.0, th * deg_s * dt))
                    if dx != 0.0 or dy != 0.0 or dz != 0.0 or dth != 0.0:
                        cmd = f"DO DMOVE {dx:.3f},{dy:.3f},{dz:.3f},{dth:.3f}"
                        self.ser.send_line(cmd)
                    time.sleep(dt)
            else:
                if mode == ControlMode.JOG_SERVER and self.ser.is_connected():
                    if time.time() - self.last_packet_time > 0.1:
                        data_str = "V 0.00 0.00 0.00 0.00 "
                        c = crc16_ccitt(data_str.encode('ascii'))
                        pkt = f"{data_str}*{c:04X}\r\n"
                        self.ser.send_raw(pkt)
                        self.last_packet_time = time.time()
                time.sleep(0.05)


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SCARA Control — Unified")
        self.geometry("1280x840")
        self.resizable(True, True)
        self.ser = SerialManager()
        self.ser.monitor_callback = self.on_serial_line
        # Input/jog state
        self.pad_q = queue.Queue()
        self.stop_event = threading.Event()
        self.kb_state = dict(x=0.0, y=0.0, z=0.0, theta=0.0, deadman=False)
        # Jog state for streamer
        self.xy_pad = dict(x=0.0, y=0.0)
        self.var_jog_enable = tk.BooleanVar(value=False)
        self.var_xy_speed = tk.DoubleVar(value=200.0)
        self.var_z_speed = tk.DoubleVar(value=100.0)
        self.var_z_vel = tk.DoubleVar(value=0.0)
        self.jog_target = dict(x=0.0, y=0.0, z=250.0, r=0.0)
        self._jog_reset = True
        self.var_use_do = tk.BooleanVar(value=False)
        self._jog_last_sent = None
        self.bind_all("<KeyPress>", self.on_key_press)
        self.bind_all("<KeyRelease>", self.on_key_release)
        self.control_mode = ControlMode.MONITOR_STREAM if 'ControlMode' in globals() else None
        self.var_autoscroll = tk.BooleanVar(value=True)
        self.var_autotrim = tk.BooleanVar(value=True)
        self.var_trim_lines = tk.IntVar(value=5000)
        self.var_keep_lines = tk.IntVar(value=4000)
        self.stream_running = False
        self._last_fb = None
        self._build_connection_bar()
        self.panes = ttk.Panedwindow(self, orient="horizontal")
        self.panes.pack(fill="both", expand=True)
        self.top_container = ttk.Frame(self.panes)
        self.bottom_monitor = ttk.Frame(self.panes)
        self.panes.add(self.top_container, weight=3)
        self.panes.add(self.bottom_monitor, weight=1)
        self.nb = ttk.Notebook(self.top_container)
        self.nb.pack(fill="both", expand=True)
        self.tab_jog = ttk.Frame(self.nb)
        self.tab_editor = ttk.Frame(self.nb)
        self.tab_keyframes = ttk.Frame(self.nb)
        self.nb.add(self.tab_jog, text="Jog")
        self.nb.add(self.tab_editor, text="V+ File Manager")
        self.nb.add(self.tab_keyframes, text="Keyframes")
        self._build_jog_tab()
        self._build_editor_tab()
        self._build_keyframes_tab()
        self._build_monitor_panel()
        # Threads
        self.gamepad = None
        self.jog_loop = None
        self.after(200, self._periodic_ui)
        # Start streamer jog loop
        try:
            self.jog_thread = threading.Thread(target=self._streamer_jog_loop, daemon=True)
            self.jog_thread.start()
        except Exception:
            self.jog_thread = None

    def _build_connection_bar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="Port:").pack(side="left")
        self.cbo_port = ttk.Combobox(bar, width=22, state="readonly")
        self.cbo_port.pack(side="left", padx=5)
        ttk.Button(bar, text="Refresh", command=self.refresh_ports).pack(side="left")
        ttk.Label(bar, text="Baud:").pack(side="left", padx=(12, 0))
        self.cbo_baud = ttk.Combobox(bar, values=["9600","19200","38400","57600","115200"], width=8, state="readonly")
        self.cbo_baud.set("9600")
        self.cbo_baud.pack(side="left", padx=5)
        self.btn_connect = ttk.Button(bar, text="Connect", command=self.toggle_connect)
        self.btn_connect.pack(side="left", padx=10)
        self.lbl_conn = ttk.Label(bar, text="Disconnected", foreground="red")
        self.lbl_conn.pack(side="left", padx=12)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        self.lbl_status = ttk.Label(bar, text="Idle")
        self.lbl_status.pack(side="left")
        self.refresh_ports()

    def refresh_ports(self):
        ports = self.ser.ports()
        self.cbo_port['values'] = ports
        if ports and not self.cbo_port.get():
            self.cbo_port.current(0)

    def toggle_connect(self):
        if self.ser.is_connected():
            self.ser.disconnect()
            self.btn_connect.config(text="Connect")
            self.lbl_conn.config(text="Disconnected", foreground="red")
            return
        port = self.cbo_port.get()
        if not port:
            messagebox.showwarning("Port required", "Select a serial port")
            return
        try:
            baud = int(self.cbo_baud.get())
        except Exception:
            baud = 9600
        try:
            self.ser.connect(port, baud)
            self.btn_connect.config(text="Disconnect")
            self.lbl_conn.config(text=f"Connected: {port} @ {baud}", foreground="green")
            # Set a safe default speed (older V+ may not accept ALWAYS)
            self.ser.send_line("SPEED 30")
        except Exception as e:
            messagebox.showerror("Serial Error", str(e))

    def set_status(self, text: str):
        self.lbl_status.config(text=text)

    def _is_typing(self):
        w = None
        try:
            w = self.focus_get()
        except Exception:
            w = None
        try:
            cls = w.winfo_class() if w else ''
        except Exception:
            cls = ''
        return cls in ('Entry', 'TEntry', 'Text')

    def _build_jog_tab(self):
        frm = self.tab_jog
        # Robot commands
        rfrm = ttk.LabelFrame(frm, text="Robot")
        rfrm.pack(fill="x", padx=10, pady=8)
        ttk.Button(rfrm, text="ENABLE POWER", command=lambda: self._send_line("ENABLE POWER")).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(rfrm, text="DISABLE POWER", command=lambda: self._send_line("DISABLE POWER")).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(rfrm, text="CALIBRATE", command=self._calibrate_sequence).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(rfrm, text="Legacy Move...", command=self._legacy_move_prompt).grid(row=1, column=0, padx=6, pady=6, sticky="w")
        ttk.Button(rfrm, text="ABORT", command=lambda: self._send_line("ABORT")).grid(row=1, column=1, padx=6, pady=6, sticky="w")

        info = ttk.Label(
            frm,
            text=(
                "Use Legacy Move for single points.\n"
                "Use Streamer (V+) to upload/start the STREAM program and send x y z r lines."
            ),
            foreground="#444",
            anchor="w",
            justify="left",
        )
        info.pack(fill="x", padx=12, pady=4)

        # Legacy POINT/MOVE test controls
        lfrm = ttk.LabelFrame(frm, text="Legacy POINT/MOVE")
        lfrm.pack(fill="x", padx=10, pady=8)
        self.leg_x = tk.DoubleVar(value=0.0)
        self.leg_y = tk.DoubleVar(value=0.0)
        self.leg_z = tk.DoubleVar(value=250.0)
        self.leg_r = tk.DoubleVar(value=180.0)
        ttk.Label(lfrm, text="X").grid(row=0, column=0, padx=4, sticky="w")
        ttk.Entry(lfrm, width=8, textvariable=self.leg_x).grid(row=0, column=1)
        ttk.Label(lfrm, text="Y").grid(row=0, column=2, padx=4, sticky="w")
        ttk.Entry(lfrm, width=8, textvariable=self.leg_y).grid(row=0, column=3)
        ttk.Label(lfrm, text="Z").grid(row=0, column=4, padx=4, sticky="w")
        ttk.Entry(lfrm, width=8, textvariable=self.leg_z).grid(row=0, column=5)
        ttk.Label(lfrm, text="R").grid(row=0, column=6, padx=4, sticky="w")
        ttk.Entry(lfrm, width=8, textvariable=self.leg_r).grid(row=0, column=7)
        ttk.Button(lfrm, text="MOVE", command=self._legacy_move_btn).grid(row=0, column=8, padx=8)

        # Streamer (V+) controls
        sfrm2 = ttk.LabelFrame(frm, text="Streamer (V+)")
        sfrm2.pack(fill="x", padx=10, pady=8)
        ttk.Button(sfrm2, text="Deploy STREAM", command=self._stream_deploy).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(sfrm2, text="Start STREAM", command=self._stream_start).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(sfrm2, text="Stop", command=self._stream_stop).grid(row=0, column=2, padx=6, pady=6)
        ttk.Button(sfrm2, text="WHERE", command=self._stream_where).grid(row=0, column=3, padx=12, pady=6)
        self.stream_x = tk.DoubleVar(value=0.0)
        self.stream_y = tk.DoubleVar(value=0.0)
        self.stream_z = tk.DoubleVar(value=250.0)
        self.stream_r = tk.DoubleVar(value=0.0)
        ttk.Label(sfrm2, text="X").grid(row=1, column=0, padx=4, sticky="w")
        ttk.Entry(sfrm2, width=8, textvariable=self.stream_x).grid(row=1, column=1)
        ttk.Label(sfrm2, text="Y").grid(row=1, column=2, padx=4, sticky="w")
        ttk.Entry(sfrm2, width=8, textvariable=self.stream_y).grid(row=1, column=3)
        ttk.Label(sfrm2, text="Z").grid(row=1, column=4, padx=4, sticky="w")
        ttk.Entry(sfrm2, width=8, textvariable=self.stream_z).grid(row=1, column=5)
        ttk.Label(sfrm2, text="R").grid(row=1, column=6, padx=4, sticky="w")
        ttk.Entry(sfrm2, width=8, textvariable=self.stream_r).grid(row=1, column=7)
        ttk.Button(sfrm2, text="Send Pose", command=self._stream_send).grid(row=1, column=8, padx=8)
        # Jogging controls
        jfrm = ttk.Frame(sfrm2)
        jfrm.grid(row=2, column=0, columnspan=9, sticky="we", padx=6, pady=6)
        ttk.Checkbutton(jfrm, text="Enable Jog (hold SHIFT to move)", variable=self.var_jog_enable).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(jfrm, text="Reset Target", command=self._reset_jog_target).grid(row=0, column=2, padx=8)
        ttk.Checkbutton(jfrm, text="Use DO (no STREAM)", variable=self.var_use_do).grid(row=0, column=3, padx=8, sticky="w")
        ttk.Label(jfrm, text="XY speed (mm/s)").grid(row=1, column=0, sticky="w")
        ttk.Scale(jfrm, from_=10, to=600, orient="horizontal", variable=self.var_xy_speed).grid(row=1, column=1, sticky="we", padx=6)
        ttk.Label(jfrm, text="Z speed (mm/s)").grid(row=2, column=0, sticky="w")
        ttk.Scale(jfrm, from_=5, to=300, orient="horizontal", variable=self.var_z_speed).grid(row=2, column=1, sticky="we", padx=6)
        jfrm.grid_columnconfigure(1, weight=1)
        # SCARA jog preview with click-to-move and Z slider
        padwrap = ttk.Frame(jfrm)
        padwrap.grid(row=3, column=0, columnspan=4, sticky="w", pady=6)
        def _get_r():
            try:
                return float(self.stream_r.get())
            except Exception:
                return 0.0
        self.scara_pad = ScaraJogPad(padwrap, send_abs_cb=self._pad_send_abs, get_r_cb=_get_r, width=360, height=360)
        self.scara_pad.pack(side="left")

    def _on_mode_change(self, event=None):
        pass

    def _make_slider(self, parent, label, var, mn, mx, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        s = ttk.Scale(parent, from_=mn, to=mx, orient="horizontal", variable=var)
        s.grid(row=row, column=1, sticky="we", padx=6, pady=4)
        parent.grid_columnconfigure(1, weight=1)
        e = ttk.Entry(parent, width=6, textvariable=var)
        e.grid(row=row, column=2, padx=6, pady=4)

    def _send_line(self, s: str):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        if self.control_mode == ControlMode.JOG_SERVER and s.strip():
            messagebox.showinfo("Mode", "In Jog Server mode, use controller-driven motion. Switch to Monitor mode for manual commands.")
            return
        self.ser.send_line(s)

    def _pad_send_abs(self, x: float, y: float, z: float, r: float):
        if not self.ser.is_connected():
            return
        x, y, z, r, _ = clamp_abs(x, y, z, r)
        line = f"{x:.2f},{y:.2f},{z:.2f},{r:.2f}"
        if self.var_use_do.get() or not self.stream_running:
            self.ser.send_line(f"DO MOVE TRANS({x:.2f},{y:.2f},{z:.2f},0,180,{r:.2f})")
        else:
            self.ser.send_line(line)
        try:
            self.set_status(f"Move → {line}")
        except Exception:
            pass

    # --- XY pad and jog helpers ---
    def _xy_pad_draw(self):
        try:
            c = self.xy_canvas
        except Exception:
            return
        c.delete('all')
        w = int(c['width']); h = int(c['height'])
        cx = w//2; cy = h//2; r = min(w, h)//2 - 10
        # axes
        c.create_line(10, cy, w-10, cy, fill="#666")
        c.create_line(cx, 10, cx, h-10, fill="#666")
        # circle
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline="#444")
        # dot
        x = max(-1.0, min(1.0, float(self.xy_pad.get('x', 0.0))))
        y = max(-1.0, min(1.0, float(self.xy_pad.get('y', 0.0))))
        px = cx + int(x * r)
        py = cy - int(y * r)
        c.create_oval(px-6, py-6, px+6, py+6, fill="#0cf", outline="")

    def _xy_pad_down(self, event):
        self._xy_pad_set_from_event(event)

    def _xy_pad_drag(self, event):
        self._xy_pad_set_from_event(event)

    def _xy_pad_up(self, event):
        self.xy_pad['x'] = 0.0
        self.xy_pad['y'] = 0.0
        self._xy_pad_draw()

    def _xy_pad_set_from_event(self, event):
        c = self.xy_canvas
        w = int(c['width']); h = int(c['height'])
        cx = w//2; cy = h//2; r = min(w, h)//2 - 10
        dx = (event.x - cx) / float(r)
        dy = (cy - event.y) / float(r)
        self.xy_pad['x'] = max(-1.0, min(1.0, dx))
        self.xy_pad['y'] = max(-1.0, min(1.0, dy))
        self._xy_pad_draw()

    def _reset_jog_target(self):
        if self.stream_running:
            if self._last_fb:
                self.jog_target['x'] = float(self._last_fb['x'])
                self.jog_target['y'] = float(self._last_fb['y'])
                self.jog_target['z'] = float(self._last_fb['z'])
                self.jog_target['r'] = float(self._last_fb['r'])
                try:
                    self.stream_x.set(self.jog_target['x'])
                    self.stream_y.set(self.jog_target['y'])
                    self.stream_z.set(self.jog_target['z'])
                    self.stream_r.set(self.jog_target['r'])
                except Exception:
                    pass
                self._jog_reset = False
                return
            # No feedback yet, fall back to message
            messagebox.showinfo("Reset Target", "Waiting for feedback (FB) from STREAM. Try after moving or stop STREAM.")
            return
        pos = self._query_position()
        if pos:
            self.jog_target['x'] = float(pos['x'])
            self.jog_target['y'] = float(pos['y'])
            self.jog_target['z'] = float(pos['z'])
            self.jog_target['r'] = float(pos['theta'])
            try:
                self.stream_x.set(self.jog_target['x'])
                self.stream_y.set(self.jog_target['y'])
                self.stream_z.set(self.jog_target['z'])
                self.stream_r.set(self.jog_target['r'])
            except Exception:
                pass
            self._jog_reset = False
        else:
            self._jog_reset = True

    def _streamer_jog_loop(self):
        rate = 20.0
        dt = 1.0 / rate
        last_reset_try = 0.0
        while True:
            try:
                time.sleep(dt)
                if not self.ser.is_connected():
                    continue
                if not self.var_jog_enable.get():
                    continue
                dead = bool(self.kb_state.get('deadman', False))
                if not dead:
                    continue
                # Initialize target from WHERE once
                now = time.time()
                if self._jog_reset and now - last_reset_try > 0.5:
                    last_reset_try = now
                    if self.stream_running:
                        # Seed from last feedback if available, else from UI fields
                        if getattr(self, '_last_fb', None):
                            self.jog_target['x'] = float(self._last_fb['x'])
                            self.jog_target['y'] = float(self._last_fb['y'])
                            self.jog_target['z'] = float(self._last_fb['z'])
                            self.jog_target['r'] = float(self._last_fb['r'])
                            self._jog_reset = False
                        else:
                            try:
                                self.jog_target['x'] = float(self.stream_x.get())
                                self.jog_target['y'] = float(self.stream_y.get())
                                self.jog_target['z'] = float(self.stream_z.get())
                                self.jog_target['r'] = float(self.stream_r.get())
                                self._jog_reset = False
                            except Exception:
                                pass
                        if self._jog_reset:
                            continue
                    else:
                        self._reset_jog_target()
                        if self._jog_reset:
                            continue
                # velocities from XY pad and keyboard overrides
                vx = float(self.xy_pad.get('x', 0.0)) * float(self.var_xy_speed.get())
                vy = float(self.xy_pad.get('y', 0.0)) * float(self.var_xy_speed.get())
                # keyboard overrides if stronger
                if abs(self.kb_state.get('x', 0.0)) > abs(self.xy_pad.get('x', 0.0)):
                    vx = float(self.kb_state.get('x', 0.0)) * float(self.var_xy_speed.get())
                if abs(self.kb_state.get('y', 0.0)) > abs(self.xy_pad.get('y', 0.0)):
                    vy = float(self.kb_state.get('y', 0.0)) * float(self.var_xy_speed.get())
                vz = float(self.var_z_vel.get()) * float(self.var_z_speed.get())
                if abs(self.kb_state.get('z', 0.0)) > abs(self.var_z_vel.get()):
                    vz = float(self.kb_state.get('z', 0.0)) * float(self.var_z_speed.get())
                # integrate small step
                self.jog_target['x'] += vx * dt
                self.jog_target['y'] += vy * dt
                self.jog_target['z'] += vz * dt
                should_send = False
                if self._jog_last_sent is None:
                    should_send = True
                else:
                    dx = abs(self.jog_target['x'] - self._jog_last_sent['x'])
                    dy = abs(self.jog_target['y'] - self._jog_last_sent['y'])
                    dz = abs(self.jog_target['z'] - self._jog_last_sent['z'])
                    dr = abs(self.jog_target['r'] - self._jog_last_sent['r'])
                    if (dx + dy + dz) > 0.2 or dr > 0.2:
                        should_send = True
                if not should_send:
                    continue
                if self.var_use_do.get():
                    cx, cy, cz, cr, _clamped = clamp_abs(self.jog_target['x'], self.jog_target['y'],
                                                         self.jog_target['z'], self.jog_target['r'])
                    if _clamped:
                        try:
                            self.set_status("CLAMPED to safe envelope")
                        except Exception:
                            pass
                    self.ser.send_line(
                        f"DO MOVE TRANS({cx:.2f},{cy:.2f},{cz:.2f},0,180,{cr:.2f})"
                    )
                else:
                    if not self.stream_running:
                        continue
                    # Send absolute clamped targets to STREAM (ABS mode)
                    if self._jog_last_sent is None:
                        self._jog_last_sent = dict(self.jog_target)
                        continue
                    cx, cy, cz, cr, _clamped = clamp_abs(self.jog_target['x'], self.jog_target['y'],
                                                          self.jog_target['z'], self.jog_target['r'])
                    if _clamped:
                        try:
                            self.set_status("CLAMPED to safe envelope")
                        except Exception:
                            pass
                    line = f"{cx:.2f},{cy:.2f},{cz:.2f},{cr:.2f}"
                    self.ser.send_line(line)
                self._jog_last_sent = dict(self.jog_target)
            except Exception:
                time.sleep(0.1)

    def _calibrate_sequence(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        def worker():
            try:
                self.set_status("Calibrating...")
                self.ser.send_line("CALIBRATE")
                time.sleep(0.6)
                self.ser.send_line("Y")
                time.sleep(0.5)
                # Send Y again in case the prompt re-asked
                self.ser.send_line("Y")
                time.sleep(0.2)
            finally:
                self.set_status("Idle")
        threading.Thread(target=worker, daemon=True).start()

    def on_key_press(self, event):
        k = event.keysym
        allowed = {
            'Shift_L','Shift_R','Left','Right','Up','Down',
            'Prior','Page_Up','Next','Page_Down','bracketleft','bracketright'
        }
        if self._is_typing() and k not in allowed:
            return
        if k in ('Shift_L', 'Shift_R'):
            self.kb_state['deadman'] = True
        elif k == 'Left':
            self.kb_state['x'] = -1.0
        elif k == 'Right':
            self.kb_state['x'] = 1.0
        elif k == 'Up':
            self.kb_state['y'] = 1.0
        elif k == 'Down':
            self.kb_state['y'] = -1.0
        elif k in ('Prior', 'Page_Up'):
            self.kb_state['z'] = 1.0
        elif k in ('Next', 'Page_Down'):
            self.kb_state['z'] = -1.0
        elif k == 'bracketleft':
            self.kb_state['theta'] = -1.0
        elif k == 'bracketright':
            self.kb_state['theta'] = 1.0

    def on_key_release(self, event):
        k = event.keysym
        allowed = {
            'Shift_L','Shift_R','Left','Right','Up','Down',
            'Prior','Page_Up','Next','Page_Down','bracketleft','bracketright'
        }
        if self._is_typing() and k not in allowed:
            return
        if k in ('Shift_L', 'Shift_R'):
            self.kb_state['deadman'] = False
        elif k in ('Left', 'Right'):
            self.kb_state['x'] = 0.0
        elif k in ('Up', 'Down'):
            self.kb_state['y'] = 0.0
        elif k in ('Prior', 'Page_Up', 'Next', 'Page_Down'):
            self.kb_state['z'] = 0.0
        elif k in ('bracketleft', 'bracketright'):
            self.kb_state['theta'] = 0.0

    def _periodic_ui(self):
        # No periodic updates needed in simplified app
        self.after(500, self._periodic_ui)

    def _build_editor_tab(self):
        frm = self.tab_editor
        toolbar = ttk.Frame(frm)
        toolbar.pack(side="top", fill="x", padx=6, pady=6)
        ttk.Button(toolbar, text="List", command=self._vplus_list).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Download", command=self._vplus_download).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Upload", command=self._vplus_upload).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete", command=self._vplus_delete).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Custom...", command=self._vplus_custom).pack(side="left", padx=8)
        ttk.Button(toolbar, text="Open .v", command=self._open_v_file).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Save", command=self._save_v_file).pack(side="left", padx=2)
        self.editor = scrolledtext.ScrolledText(frm, wrap="none", font=("Courier New", 10))
        self.editor.pack(fill="both", expand=True, padx=8, pady=6)
        self.current_prog_name = None
        self.current_prog_file = None

    def _open_v_file(self):
        fn = filedialog.askopenfilename(filetypes=[("V+ Programs", "*.v"), ("All", "*.*")])
        if not fn:
            return
        try:
            with open(fn, 'r') as f:
                txt = f.read()
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", txt)
            self.current_prog_file = fn
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _save_v_file(self):
        if not self.current_prog_file:
            fn = filedialog.asksaveasfilename(defaultextension=".v", filetypes=[("V+ Programs", "*.v"), ("All", "*.*")])
            if not fn:
                return
            self.current_prog_file = fn
        try:
            with open(self.current_prog_file, 'w') as f:
                f.write(self.editor.get("1.0", "end-1c"))
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _vplus_list(self):
        if not self.ser.is_connected():
            return
        resp = self.ser.send_command("DIR", timeout=3.0)
        progs = []
        for line in resp.split("\n"):
            m = re.search(r'(\w+)\s+PROGRAM', line, re.I)
            if m:
                progs.append(m.group(1).upper())
        text = "\n".join(sorted(set(progs))) if progs else "No programs found"
        messagebox.showinfo("Programs", text)

    def _vplus_download(self):
        if not self.ser.is_connected():
            return
        name = simpledialog.askstring("Download", "Program name:", parent=self)
        if not name:
            return
        resp = self.ser.send_command(f"LISTF {name}", timeout=5.0)
        if "ERROR" in resp.upper() or not resp.strip():
            resp = self.ser.send_command(f"LIST {name}", timeout=5.0)
        if not resp.strip():
            messagebox.showerror("Download", f"Failed to download {name}")
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", resp)
        self.current_prog_name = name.upper()

    def _vplus_upload(self):
        if not self.ser.is_connected():
            return
        source = self.editor.get("1.0", "end-1c").strip()
        if not source:
            messagebox.showwarning("Empty", "Editor is empty")
            return
        m = re.search(r'\.PROGRAM\s+(\w+)', source, re.I)
        name = m.group(1).upper() if m else self.current_prog_name
        if not name:
            name = simpledialog.askstring("Upload", "Program name:", parent=self)
        if not name:
            return
        if not messagebox.askyesno("Confirm", f"Upload '{name}' to controller?"):
            return
        self.ser.send_line(f"EDIT {name}")
        time.sleep(0.2)
        lines = source.split("\n")
        for line in lines:
            self.ser.send_line(line.rstrip())
            time.sleep(0.05)
        # End edit mode: some controllers require a single '.' line
        self.ser.send_line(".")
        time.sleep(0.2)
        self.current_prog_name = name
        messagebox.showinfo("Upload", f"Upload complete: {name}")

    def _vplus_delete(self):
        if not self.ser.is_connected():
            return
        name = simpledialog.askstring("Delete", "Program name:", parent=self)
        if not name:
            return
        if not messagebox.askyesno("Confirm", f"Delete '{name}' from controller?"):
            return
        resp = self.ser.send_command(f"DELETE {name}", timeout=3.0)
        if "ERROR" in resp.upper():
            messagebox.showerror("Delete", f"Failed to delete {name}\n{resp}")
        else:
            messagebox.showinfo("Delete", f"Deleted: {name}")

    def _vplus_custom(self):
        if not self.ser.is_connected():
            return
        cmd = simpledialog.askstring("Custom Command", "Enter V+ command:", parent=self)
        if not cmd:
            return
        resp = self.ser.send_command(cmd, timeout=3.0)
        messagebox.showinfo("Response", resp or "(no response)")

    def _build_keyframes_tab(self):
        frm = self.tab_keyframes
        top = ttk.Frame(frm)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Button(top, text="Capture FROM WHERE", command=self._kf_capture).pack(side="left", padx=4)
        ttk.Button(top, text="Delete", command=self._kf_delete).pack(side="left", padx=4)
        ttk.Label(top, text="Delay (s):").pack(side="left", padx=(16,4))
        self.var_kf_delay = tk.DoubleVar(value=0.3)
        ttk.Entry(top, width=6, textvariable=self.var_kf_delay).pack(side="left")
        ttk.Button(top, text="Play Once", command=lambda: self._kf_play(loop=1)).pack(side="left", padx=8)
        ttk.Button(top, text="Play N...", command=self._kf_play_n).pack(side="left")
        mid = ttk.Frame(frm)
        mid.pack(fill="both", expand=True, padx=10, pady=8)
        self.list_kf = tk.Listbox(mid)
        self.list_kf.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.list_kf.yview)
        sb.pack(side="left", fill="y")
        self.list_kf.config(yscrollcommand=sb.set)
        self.keyframes = []

    # --- Streamer (V+) helpers ---
    def _stream_program_source(self) -> str:
        return "\n".join([
            ".PROGRAM STREAM",
            "LOCAL $in, $tok",
            "LOCAL REAL x, y, z, r, rad2, sc, rad",
            "ATTACH (4) \"MONITOR\"",
            "TYPE \"FB READY\"",
            "10 READ (4) $in",
            "$tok = $DECODE($in, \" ,\", 0)",
            "IF $tok == \"STOP\" THEN",
            "  TYPE \"FB STOP\"",
            "  STOP",
            "END",
            "x = VAL($tok)",
            "$tok = $DECODE($in, \" ,\", 1)",
            "$tok = $DECODE($in, \" ,\", 0)",
            "y = VAL($tok)",
            "$tok = $DECODE($in, \" ,\", 1)",
            "$tok = $DECODE($in, \" ,\", 0)",
            "z = VAL($tok)",
            "$tok = $DECODE($in, \" ,\", 1)",
            "$tok = $DECODE($in, \" ,\", 0)",
            "r = VAL($tok)",
            "IF z < 185 THEN",
            "  z = 185",
            "END",
            "IF z > 380 THEN",
            "  z = 380",
            "END",
            "IF x < 0 THEN",
            "  IF y >= 0 THEN",
            "    IF y < 150 THEN",
            "      y = 150",
            "    END",
            "  END",
            "  IF y < 0 THEN",
            "    IF -y < 150 THEN",
            "      y = -150",
            "    END",
            "  END",
            "END",
            "rad2 = x*x + y*y",
            "IF rad2 > 0.001 THEN",
            "  IF rad2 < 32400 THEN",
            "    sc = 180 / SQRT(rad2)",
            "    x = x * sc",
            "    y = y * sc",
            "  END",
            "  IF rad2 > 313600 THEN",
            "    sc = 560 / SQRT(rad2)",
            "    x = x * sc",
            "    y = y * sc",
            "  END",
            "  rad2 = x*x + y*y",
            "  rad = SQRT(rad2)",
            "  IF x < (-0.173648 * rad) THEN",
            "    x = -0.173648 * rad",
            "    IF y >= 0 THEN",
            "      y = SQRT(rad2 - x*x)",
            "    ELSE",
            "      y = -SQRT(rad2 - x*x)",
            "    END",
            "  END",
            "END",
            "MOVE TRANS(x, y, z, 0, 180, r)",
            "TYPE \"FB \", x, \",\", y, \",\", z, \",\", r",
            "GOTO 10",
        ])

    def _stream_deploy(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        src = self._stream_program_source().split("\n")
        try:
            # Ensure no task is active
            self.ser.send_line("ABORT")
            time.sleep(0.2)
            # Delete any existing program named STREAM so line 1 is available
            self.ser.send_line("DELETEP STREAM")
            time.sleep(0.2)
            self.ser.send_line("EDIT STREAM")
            time.sleep(0.2)
            # Enter insert mode so we append cleanly at step 2
            self.ser.send_line("I")
            time.sleep(0.1)
            for ln in src:
                if ln.strip().upper().startswith('.PROGRAM'):
                    continue
                clean = ln.lstrip()
                if not clean:
                    continue
                self.ser.send_line(clean)
                time.sleep(0.06)
            # Exit editor (Edit F1/B0)
            self.ser.send_line("E")
            time.sleep(0.2)
            messagebox.showinfo("Deploy", "STREAM program uploaded.")
        except Exception as e:
            messagebox.showerror("Deploy", str(e))

    def _stream_start(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        # Ensure speed is set
        self.ser.send_line("SPEED 30")
        # Seed jog target from current position before starting program
        try:
            self._reset_jog_target()
        except Exception:
            pass
        time.sleep(0.05)
        self.ser.send_line("EXECUTE STREAM")
        self.stream_running = True
        self._jog_reset = False

    def _stream_stop(self):
        if not self.ser.is_connected():
            return
        # Prefer in-band STOP so READ can terminate cleanly; fall back to ABORT when not running
        if self.stream_running:
            self.ser.send_line("STOP")
            self.stream_running = False
        else:
            self.ser.send_line("ABORT")

    def _stream_send(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        # Send a line of four numbers; the STREAM program reads them
        x, y, z, r = map(float, (self.stream_x.get(), self.stream_y.get(), self.stream_z.get(), self.stream_r.get()))
        x, y, z, r, _clamped = clamp_abs(x, y, z, r)
        if _clamped:
            try:
                self.set_status("CLAMPED to safe envelope")
            except Exception:
                pass
        if self.var_use_do.get():
            self.ser.send_line(f"DO MOVE TRANS({x:.2f},{y:.2f},{z:.2f},0,180,{r:.2f})")
        else:
            line = f"{x:.2f},{y:.2f},{z:.2f},{r:.2f}"
            self.ser.send_line(line)

    def _stream_where(self):
        if not self.ser.is_connected():
            return
        # Only works if STREAM is not currently attached; otherwise it will consume the line
        if self.stream_running:
            messagebox.showinfo("WHERE", "Stop STREAM before issuing monitor commands.")
            return
        self.ser.send_line("WHERE")

    def _query_position(self):
        if not self.ser.is_connected():
            return None
        resp = self.ser.send_command("WHERE", timeout=1.2)
        # Format 1: TRANS(x,y,z,theta)
        m = re.search(r'TRANS\s*\(\s*([\-\d.]+)\s*,\s*([\-\d.]+)\s*,\s*([\-\d.]+)\s*,\s*([\-\d.]+)', resp)
        if m:
            return dict(x=float(m.group(1)), y=float(m.group(2)), z=float(m.group(3)), theta=float(m.group(4)))
        # Format 2: Labeled X: Y: Z: T:
        mx = re.search(r'X[:\s]+([\-\d.]+)', resp, re.I)
        my = re.search(r'Y[:\s]+([\-\d.]+)', resp, re.I)
        mz = re.search(r'Z[:\s]+([\-\d.]+)', resp, re.I)
        mt = re.search(r'T[:\s]+([\-\d.]+)', resp, re.I)
        if mx and my and mz and mt:
            return dict(x=float(mx.group(1)), y=float(my.group(1)), z=float(mz.group(1)), theta=float(mt.group(1)))
        # Format 3: Table with X Y Z y p r Hand followed by numbers -> take r as theta
        lines = [ln.strip() for ln in resp.splitlines() if ln.strip()]
        vals_xyzr = None
        for ln in lines:
            nums = re.findall(r'[-+]?\d+(?:\.\d+)?', ln)
            if len(nums) >= 6:
                if re.search(r'\bX\b.*\bY\b.*\bZ\b.*\by\b.*\bp\b.*\br\b', resp):
                    vals_xyzr = list(map(float, nums[:6]))
                    break
        if vals_xyzr:
            x, y, z, _y_ang, _p_ang, r_ang = vals_xyzr
            return dict(x=float(x), y=float(y), z=float(z), theta=float(r_ang))
        return None

    def _kf_capture(self):
        pos = self._query_position()
        if not pos:
            messagebox.showwarning("WHERE", "Failed to read position")
            return
        label = simpledialog.askstring("Label", "Keyframe label:", parent=self) or (
            f"X{pos['x']:.1f} Y{pos['y']:.1f} Z{pos['z']:.1f} T{pos['theta']:.1f}")
        self.keyframes.append(dict(label=label, pos=pos))
        self.list_kf.insert("end", label)

    def _kf_delete(self):
        sel = list(self.list_kf.curselection())
        if not sel:
            return
        idx = sel[0]
        self.list_kf.delete(idx)
        del self.keyframes[idx]

    def _kf_play(self, loop=1):
        if not self.ser.is_connected():
            return
        if not self.keyframes:
            return
        delay = float(self.var_kf_delay.get())
        seq = [kf['pos'] for kf in self.keyframes]
        def worker():
            for _ in range(loop):
                for p in seq:
                    cmd = f"DO MOVE(TRANS({p['x']:.2f},{p['y']:.2f},{p['z']:.2f},{p['theta']:.2f}))"
                    self.ser.send_line(cmd)
                    time.sleep(delay)
        threading.Thread(target=worker, daemon=True).start()

    def _kf_play_n(self):
        n = simpledialog.askinteger("Repeat", "Repeat N times:", parent=self, minvalue=1, maxvalue=1000)
        if not n:
            return
        self._kf_play(loop=n)

    def _legacy_move_btn(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        x, y, z, r = map(float, (self.leg_x.get(), self.leg_y.get(), self.leg_z.get(), self.leg_r.get()))
        x, y, z, r, _clamped = clamp_abs(x, y, z, r)
        if _clamped:
            try:
                self.set_status("CLAMPED to safe envelope")
            except Exception:
                pass
        # Legacy flow: define point 'a' with 6 fields x,y,z,yaw,pitch,roll and then DO MOVE a
        # We mimic the old script's orientation: yaw=0.00, pitch=180, roll=r
        self.ser.send_line("POINT a")
        time.sleep(0.05)
        self.ser.send_line(f"{x:.2f},{y:.2f},{z:.2f},0.00,180,{r:.2f}")
        time.sleep(0.05)
        self.ser.send_line("")  # terminate POINT entry
        time.sleep(0.05)
        self.ser.send_line("DO MOVE a")

    def _legacy_move_prompt(self):
        if not self.ser.is_connected():
            messagebox.showwarning("Not connected", "Connect to serial first")
            return
        pos = self._query_position() or {}
        def askf(title, prompt, val):
            try:
                return simpledialog.askfloat(title, prompt, initialvalue=float(val) if val is not None else None, parent=self)
            except Exception:
                return simpledialog.askfloat(title, prompt, parent=self)
        x = askf("Legacy Move", "X (mm):", pos.get('x', 0.0))
        if x is None:
            return
        y = askf("Legacy Move", "Y (mm):", pos.get('y', 0.0))
        if y is None:
            return
        z = askf("Legacy Move", "Z (mm):", pos.get('z', 250.0))
        if z is None:
            return
        r = askf("Legacy Move", "R (deg):", pos.get('theta', 180.0))
        if r is None:
            return
        x, y, z, r, _clamped = clamp_abs(x, y, z, r)
        if _clamped:
            try:
                self.set_status("CLAMPED to safe envelope")
            except Exception:
                pass
        # Send the legacy sequence
        self.ser.send_line("POINT a")
        time.sleep(0.05)
        self.ser.send_line(f"{x:.2f},{y:.2f},{z:.2f},0.00,180,{r:.2f}")
        time.sleep(0.05)
        self.ser.send_line("")
        time.sleep(0.05)
        self.ser.send_line("DO MOVE a")

    def _build_monitor_panel(self):
        frm = self.bottom_monitor
        top = ttk.Frame(frm)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="Clear", command=self._monitor_clear).pack(side="left")
        ttk.Checkbutton(top, text="Autoscroll", variable=self.var_autoscroll).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(top, text="Auto-trim", variable=self.var_autotrim).pack(side="left", padx=(12, 0))
        ttk.Label(top, text="Trim at lines:").pack(side="left", padx=(16, 4))
        ttk.Entry(top, width=6, textvariable=self.var_trim_lines).pack(side="left")
        ttk.Label(top, text="Keep lines:").pack(side="left", padx=(12, 4))
        ttk.Entry(top, width=6, textvariable=self.var_keep_lines).pack(side="left")
        cmd = ttk.Frame(frm)
        cmd.pack(fill="x", padx=8, pady=(0,6))
        ttk.Label(cmd, text="Command:").pack(side="left")
        self.cmd_entry = ttk.Entry(cmd)
        self.cmd_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.cmd_entry.bind('<Return>', self._on_send_cmd)
        self.cmd_entry.bind('<KP_Enter>', self._on_send_cmd)
        ttk.Button(cmd, text="Send", command=self._on_send_cmd).pack(side="left")
        self.monitor = scrolledtext.ScrolledText(frm, wrap="word", font=("Courier New", 9),
                                                 background="#111", foreground="#e6e6e6")
        self.monitor.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.monitor.config(state="disabled")

    def _monitor_clear(self):
        self.monitor.config(state="normal")
        self.monitor.delete("1.0", "end")
        self.monitor.config(state="disabled")
        

    def _on_send_cmd(self, event=None):
        try:
            txt = self.cmd_entry.get().strip()
        except Exception:
            txt = ''
        if not txt:
            return 'break'
        self._send_line(txt)
        try:
            self.cmd_entry.delete(0, 'end')
        except Exception:
            pass
        return 'break'

    def on_serial_line(self, line: str):
        try:
            m = re.search(r"^\s*FB(\s+REL)?[\s,]+([-+]?\d+(?:\.\d+)?)[\s,]+([-+]?\d+(?:\.\d+)?)[\s,]+([-+]?\d+(?:\.\d+)?)[\s,]+([-+]?\d+(?:\.\d+)?)\s*$", line)
            if m:
                is_rel = bool(m.group(1))
                fx, fy, fz, fr = map(float, m.groups()[1:])
                if not is_rel:
                    self._last_fb = dict(x=fx, y=fy, z=fz, r=fr)
                    def upd():
                        try:
                            self.stream_x.set(fx)
                            self.stream_y.set(fy)
                            self.stream_z.set(fz)
                            self.stream_r.set(fr)
                            if hasattr(self, 'scara_pad') and self.scara_pad:
                                self.scara_pad.set_feedback(fx, fy, fz, fr)
                        except Exception:
                            pass
                    self.after(0, upd)
            elif line.strip().upper().startswith("FB STOP"):
                self.stream_running = False
            elif line.strip().upper().startswith("FB READY"):
                # Program is alive; allow jogging even before first FB numbers
                self._jog_reset = False
            elif re.search(r"Program task\s+\d+\s+stopped", line, re.IGNORECASE):
                # Program halted due to error; stop streaming and prevent further jog sends
                self.stream_running = False
                self._jog_last_sent = None
        except Exception:
            pass
        self.after(0, lambda: self._append_monitor(line))

    def _append_monitor(self, line: str):
        s = (line + "\n")
        self.monitor.config(state="normal")
        self.monitor.insert("end", s)
        if self.var_autoscroll.get():
            self.monitor.see("end")
        self.monitor.config(state="disabled")
        if self.var_autotrim.get():
            try:
                lines_total = int(self.monitor.index('end-1c').split('.')[0])
                trim_at = max(100, int(self.var_trim_lines.get()))
                keep = max(50, min(int(self.var_keep_lines.get()), trim_at))
                if lines_total > trim_at:
                    start_line = lines_total - keep + 1
                    self.monitor.config(state="normal")
                    self.monitor.delete("1.0", f"{start_line}.0")
                    self.monitor.config(state="disabled")
            except Exception:
                pass


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
