#!/usr/bin/env python3
"""
V+ Program Editor & Uploader - Edit and upload V+ programs without old Adept software
Requirements: pip install pyserial
"""

import sys, time, re, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog, simpledialog

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("Install: pip install pyserial")
    sys.exit(1)

class VPlusTerminal:
    """V+ serial communication handler"""
    def __init__(self):
        self.ser = None
        self.read_thread = None
        self.stop_event = threading.Event()
        self.response_queue = queue.Queue()
        self.monitor_callback = None
    
    def connect(self, port, baud=9600):
        self.disconnect()
        self.ser = serial.Serial(port, baud, timeout=0.1, write_timeout=1.0)
        time.sleep(0.2)
        self.ser.reset_input_buffer()
        self.send_line("")
        time.sleep(0.1)
        
        self.stop_event.clear()
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()
        return True
    
    def disconnect(self):
        if self.read_thread:
            self.stop_event.set()
            self.read_thread.join(timeout=1.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None
    
    def is_connected(self):
        return self.ser and self.ser.is_open
    
    def send_line(self, text):
        if self.is_connected():
            self.ser.write((text + "\r").encode("ascii", errors="ignore"))
            return True
        return False
    
    def send_command(self, cmd, timeout=2.0):
        while not self.response_queue.empty():
            self.response_queue.get_nowait()
        
        self.send_line(cmd)
        response_lines = []
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            try:
                line = self.response_queue.get(timeout=0.1)
                response_lines.append(line)
                if line.strip().endswith('.') or 'ERROR' in line.upper():
                    break
            except queue.Empty:
                continue
        
        return "\n".join(response_lines)
    
    def _read_loop(self):
        buffer = ""
        while not self.stop_event.is_set():
            if not self.is_connected():
                time.sleep(0.1)
                continue
            
            try:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    text = data.decode("ascii", errors="ignore")
                    buffer += text
                    
                    while "\n" in buffer or "\r" in buffer:
                        idx = min([i for i in [buffer.find("\n"), buffer.find("\r")] if i >= 0])
                        line = buffer[:idx]
                        buffer = buffer[idx+1:]
                        
                        if line.strip():
                            self.response_queue.put(line)
                            if self.monitor_callback:
                                self.monitor_callback(line)
                
                time.sleep(0.01)
            except Exception as e:
                print(f"Read error: {e}")
    
    def list_programs(self):
        response = self.send_command("DIR", timeout=3.0)
        programs = []
        for line in response.split("\n"):
            match = re.search(r'(\w+)\s+PROGRAM', line, re.IGNORECASE)
            if match:
                programs.append(match.group(1).upper())
        return sorted(set(programs))
    
    def download_program(self, name):
        response = self.send_command(f"LISTF {name}", timeout=5.0)
        if "ERROR" in response.upper():
            response = self.send_command(f"LIST {name}", timeout=5.0)
        return response
    
    def upload_program(self, name, source, progress_callback=None):
        lines = source.strip().split("\n")
        self.send_line(f".EDIT {name}")
        time.sleep(0.2)
        
        for i, line in enumerate(lines):
            if progress_callback:
                progress_callback(i + 1, len(lines))
            self.send_line(line.rstrip())
            time.sleep(0.05)
        
        self.send_line("")
        time.sleep(0.1)
        return True
    
    def delete_program(self, name):
        response = self.send_command(f"DELETE {name}")
        return "ERROR" not in response.upper()

class VPlusEditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("V+ Program Editor & Uploader")
        self.geometry("1000x700")
        
        self.terminal = VPlusTerminal()
        self.terminal.monitor_callback = self.on_monitor_output
        self.current_file = None
        self.current_program = None
        
        self.create_widgets()
        self.create_menu()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_ports()
    
    def create_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        
        ctrl_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Controller", menu=ctrl_menu)
        ctrl_menu.add_command(label="List Programs", command=self.list_programs)
        ctrl_menu.add_command(label="Download...", command=self.download_program)
        ctrl_menu.add_command(label="Upload", command=self.upload_program, accelerator="F5")
        ctrl_menu.add_command(label="Delete...", command=self.delete_program)
        ctrl_menu.add_separator()
        ctrl_menu.add_command(label="Custom Command...", command=self.send_custom_command)
        
        self.bind("<Control-n>", lambda e: self.new_file())
        self.bind("<Control-o>", lambda e: self.open_file())
        self.bind("<Control-s>", lambda e: self.save_file())
        self.bind("<F5>", lambda e: self.upload_program())
    
    def create_widgets(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=5, pady=5)
        
        ttk.Label(toolbar, text="Port:").pack(side="left", padx=5)
        self.port_combo = ttk.Combobox(toolbar, width=15, state="readonly")
        self.port_combo.pack(side="left", padx=5)
        
        ttk.Label(toolbar, text="Baud:").pack(side="left", padx=5)
        self.baud_combo = ttk.Combobox(toolbar, values=["9600","19200","38400","57600","115200"], 
                                       width=8, state="readonly")
        self.baud_combo.set("9600")
        self.baud_combo.pack(side="left", padx=5)
        
        ttk.Button(toolbar, text="↻", width=3, command=self.refresh_ports).pack(side="left", padx=2)
        
        self.btn_connect = ttk.Button(toolbar, text="Connect", command=self.toggle_connect)
        self.btn_connect.pack(side="left", padx=5)
        
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=10)
        
        self.btn_upload = ttk.Button(toolbar, text="⬆ Upload (F5)", command=self.upload_program, state="disabled")
        self.btn_upload.pack(side="left", padx=5)
        
        self.btn_download = ttk.Button(toolbar, text="⬇ Download", command=self.download_program, state="disabled")
        self.btn_download.pack(side="left", padx=5)
        
        self.btn_list = ttk.Button(toolbar, text="📋 List", command=self.list_programs, state="disabled")
        self.btn_list.pack(side="left", padx=5)
        
        self.status_label = ttk.Label(toolbar, text="Disconnected", foreground="red")
        self.status_label.pack(side="right", padx=10)
        
        # Main content
        main_paned = ttk.PanedWindow(self, orient="vertical")
        main_paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Editor
        editor_frame = ttk.LabelFrame(main_paned, text="Program Editor")
        main_paned.add(editor_frame, weight=3)
        
        editor_container = ttk.Frame(editor_frame)
        editor_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.line_numbers = tk.Text(editor_container, width=4, padx=3, takefocus=0,
                                     border=0, background='lightgray', state='disabled',
                                     font=("Courier New", 10))
        self.line_numbers.pack(side="left", fill="y")
        
        self.editor = scrolledtext.ScrolledText(editor_container, wrap="none", 
                                                font=("Courier New", 10), undo=True)
        self.editor.pack(side="left", fill="both", expand=True)
        self.editor.bind("<KeyRelease>", self.update_line_numbers)
        
        # Monitor
        monitor_frame = ttk.LabelFrame(main_paned, text="Controller Monitor")
        main_paned.add(monitor_frame, weight=1)
        
        self.monitor = scrolledtext.ScrolledText(monitor_frame, wrap="word", height=10,
                                                 font=("Courier New", 9),
                                                 background="#1e1e1e", foreground="#d4d4d4")
        self.monitor.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Status bar
        self.info_label = ttk.Label(self, text="Ready | No file loaded", anchor="w")
        self.info_label.pack(side="bottom", fill="x", padx=5, pady=2)
        
        self.update_line_numbers()
    
    def refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_combo['values'] = ports
        if ports and not self.port_combo.get():
            self.port_combo.current(0)
    
    def toggle_connect(self):
        if self.terminal.is_connected():
            self.terminal.disconnect()
            self.btn_connect.config(text="Connect")
            self.status_label.config(text="Disconnected", foreground="red")
            self.btn_upload.config(state="disabled")
            self.btn_download.config(state="disabled")
            self.btn_list.config(state="disabled")
            self.log_monitor("Disconnected")
        else:
            port = self.port_combo.get()
            if not port:
                messagebox.showwarning("No Port", "Select a serial port")
                return
            
            try:
                baud = int(self.baud_combo.get())
                self.terminal.connect(port, baud)
                self.btn_connect.config(text="Disconnect")
                self.status_label.config(text=f"Connected: {port} @ {baud}", foreground="green")
                self.btn_upload.config(state="normal")
                self.btn_download.config(state="normal")
                self.btn_list.config(state="normal")
                self.log_monitor(f"Connected to {port} @ {baud}")
            except Exception as e:
                messagebox.showerror("Connection Error", str(e))
    
    def log_monitor(self, text, error=False):
        self.monitor.config(state="normal")
        self.monitor.insert("end", f"{'[ERROR] ' if error else ''}{text}\n")
        self.monitor.see("end")
        self.monitor.config(state="disabled")
    
    def on_monitor_output(self, line):
        self.after(0, lambda: self.log_monitor(line))
    
    def update_line_numbers(self, event=None):
        line_count = self.editor.get("1.0", "end-1c").count("\n") + 1
        line_numbers_text = "\n".join(str(i) for i in range(1, line_count + 1))
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", line_numbers_text)
        self.line_numbers.config(state="disabled")
    
    def new_file(self):
        if self.editor.edit_modified():
            response = messagebox.askyesnocancel("Unsaved", "Save changes?")
            if response is None:
                return
            elif response:
                self.save_file()
        
        self.editor.delete("1.0", "end")
        self.current_file = None
        self.info_label.config(text="New file")
    
    def open_file(self):
        filename = filedialog.askopenfilename(filetypes=[("V+ Programs", "*.v"), ("All Files", "*.*")])
        if filename:
            with open(filename, 'r') as f:
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", f.read())
            self.current_file = filename
            self.info_label.config(text=f"Loaded: {Path(filename).name}")
    
    def save_file(self):
        if self.current_file:
            with open(self.current_file, 'w') as f:
                f.write(self.editor.get("1.0", "end-1c"))
            self.info_label.config(text=f"Saved: {Path(self.current_file).name}")
        else:
            self.save_file_as()
    
    def save_file_as(self):
        filename = filedialog.asksaveasfilename(defaultextension=".v",
                                                filetypes=[("V+ Programs", "*.v"), ("All Files", "*.*")])
        if filename:
            self.current_file = filename
            self.save_file()
    
    def list_programs(self):
        if not self.terminal.is_connected():
            return
        self.log_monitor("Listing programs...")
        programs = self.terminal.list_programs()
        if programs:
            for prog in programs:
                self.log_monitor(f"  - {prog}")
        else:
            self.log_monitor("No programs found")
    
    def download_program(self):
        if not self.terminal.is_connected():
            return
        prog_name = simpledialog.askstring("Download", "Program name:", parent=self)
        if prog_name:
            self.log_monitor(f"Downloading: {prog_name}")
            source = self.terminal.download_program(prog_name.upper())
            if source and "ERROR" not in source.upper():
                self.editor.delete("1.0", "end")
                self.editor.insert("1.0", source)
                self.current_program = prog_name.upper()
                self.info_label.config(text=f"Downloaded: {prog_name}")
            else:
                self.log_monitor(f"Failed to download {prog_name}", error=True)
    
    def upload_program(self):
        if not self.terminal.is_connected():
            return
        
        source = self.editor.get("1.0", "end-1c").strip()
        if not source:
            messagebox.showwarning("Empty", "Editor is empty")
            return
        
        # Extract program name
        match = re.search(r'\.PROGRAM\s+(\w+)', source, re.IGNORECASE)
        prog_name = match.group(1).upper() if match else self.current_program
        
        if not prog_name:
            prog_name = simpledialog.askstring("Upload", "Program name:", parent=self)
        
        if prog_name:
            if messagebox.askyesno("Confirm", f"Upload '{prog_name}' to controller?"):
                self.log_monitor(f"Uploading: {prog_name}")
                
                def progress(curr, total):
                    self.log_monitor(f"Uploading line {curr}/{total}")
                
                self.terminal.upload_program(prog_name.upper(), source, progress)
                self.log_monitor(f"Upload complete: {prog_name}")
                self.current_program = prog_name.upper()
    
    def delete_program(self):
        if not self.terminal.is_connected():
            return
        prog_name = simpledialog.askstring("Delete", "Program name:", parent=self)
        if prog_name:
            if messagebox.askyesno("Confirm", f"Delete '{prog_name}' from controller?"):
                if self.terminal.delete_program(prog_name.upper()):
                    self.log_monitor(f"Deleted: {prog_name}")
                else:
                    self.log_monitor(f"Failed to delete {prog_name}", error=True)
    
    def send_custom_command(self):
        if not self.terminal.is_connected():
            return
        cmd = simpledialog.askstring("Custom Command", "Enter V+ command:", parent=self)
        if cmd:
            response = self.terminal.send_command(cmd)
            self.log_monitor(f"Command: {cmd}")
            self.log_monitor(f"Response: {response}")
    
    def on_close(self):
        self.terminal.disconnect()
        self.destroy()

if __name__ == "__main__":
    app = VPlusEditorApp()
    app.mainloop()
