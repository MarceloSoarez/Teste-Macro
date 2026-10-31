# ==============================================================================
# BLOCO 1: IMPORTAÇÃO DE BIBLIOTECAS
# ==============================================================================
import customtkinter as ctk
from tkinter import filedialog
import threading
import time
import pickle
import os
from datetime import datetime
from pynput import keyboard as pynput_keyboard
import ctypes
from ctypes import wintypes
import sys

# ==============================================================================
# BLOCO 2: VERIFICAÇÃO E ELEVAÇÃO DE PRIVILÉGIOS (MODO ADMINISTRADOR)
# Define uma função para checar se o script possui direitos de Administrador. 
# Caso não possua, reinicia o script solicitando permissão ao Windows (UAC).
# Requisito obrigatório para que a injeção de hardware e hooks globais funcionem.
# ==============================================================================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit()

# ==============================================================================
# BLOCO 3: MAPEAMENTO DE ESTRUTURAS C/C++ PARA A API DO WINDOWS
# Mapeia as estruturas de dados nativas do Windows (`MOUSEINPUT`, `KEYBDINPUT`, 
# `INPUT_UNION` e `INPUT`) via ctypes para permitir a simulação de periféricos 
# em nível de hardware real (método imune a bloqueios de anti-cheats e janelas protegidas).
# ==============================================================================
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT),
                ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD),
                ("u", INPUT_UNION)]

# ==============================================================================
# BLOCO 4: DEFINIÇÃO DE CONSTANTES HEXADECIMAIS DO WINDOWS
# Armazena os códigos hexadecimais (Flags) lidos pela função SendInput para 
# identificar movimentações de mouse, cliques de botões e estados do teclado.
# ==============================================================================
MOUSEEVENTF_MOVE = 0x0001        
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002

# ==============================================================================
# BLOCO 5: FUNÇÃO DE EMULAÇÃO DE MOUSE POR HARDWARE
# Monta o pacote de dados do tipo MOUSEINPUT e envia o comando de clique ou 
# movimentação relativa para a API do Windows processar diretamente no driver.
# ==============================================================================
def send_mouse_hardware_absolute(x, y, flags=0):
    width = ctypes.windll.user32.GetSystemMetrics(0)
    height = ctypes.windll.user32.GetSystemMetrics(1)
    
    nx = int((x * 65535) / width)
    ny = int((y * 65535) / height)
    
    extra = ctypes.c_ulong(0)
    inp = INPUT()
    inp.type = 0  
    inp.u.mi = MOUSEINPUT(nx, ny, 0, flags | MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, ctypes.pointer(extra))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

# ==============================================================================
# BLOCO 6: FUNÇÃO DE EMULAÇÃO DE TECLADO POR HARDWARE (SCANCODES FILTRADO)
# Traduz VKs genéricos em scancodes físicos exatos à esquerda para evitar bugs
# com buffers velozes (como os de teclados magnéticos com atuação responsiva).
# ==============================================================================
def send_hardware_key(vk_code, pressed=True):
    if vk_code == 0x10:    # Shift genérico -> Força Shift Esquerdo
        scan_code = 0x2A
    elif vk_code == 0x11:  # Ctrl genérico -> Força Ctrl Esquerdo
        scan_code = 0x1D
    elif vk_code == 0x12:  # Alt genérico -> Força Alt Esquerdo
        scan_code = 0x38
    else:
        scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
        
    extra = ctypes.c_ulong(0)
    inp = INPUT()
    inp.type = 1  
    
    flags = KEYEVENTF_SCANCODE
    if not pressed:
        flags |= KEYEVENTF_KEYUP
        
    inp.u.ki = KEYBDINPUT(0, scan_code, flags, 0, ctypes.pointer(extra))
    ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

# ==============================================================================
# BLOCO 7: DICIONÁRIO DE CONVERSÃO DE TECLAS DO TKINTER PARA WINDOWS VK
# Traduz os nomes das teclas capturadas pelo Tkinter/CustomTkinter em seus 
# respectivos códigos hexadecimais reconhecidos nativamente pelo sistema operacional.
# Inclui suporte para os botões adicionais do mouse (mouse4 e mouse5).
# ==============================================================================
TK_TO_VK = {
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "prior": 0x21, "next": 0x22,
    "mouse4": 0x05, "mouse5": 0x06
}

# ==============================================================================
# BLOCO 8: CONFIGURAÇÕES GERAIS DO TEMA VISUAL
# Define o tema do sistema (claro/escuro adaptável) e a paleta de cores principal da UI.
# ==============================================================================
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# ==============================================================================
# BLOCO 9: CLASSE PRINCIPAL DO APLICATIVO - INICIALIZAÇÃO DA CLASSE E VARIÁVEIS
# Declara a classe do app herdando do CTk, inicializa todas as variáveis de 
# estado interno (controle de loops, velocidade, caminhos de gravação e automações).
# ==============================================================================
class TaskMasterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TaskMaster Pro")
        self.geometry("760x180")
        self.resizable(False, False)

        self.is_recording = False
        self.is_playing = False
        self.is_changing_hotkeys = False  
        self.ignore_mouse_enabled = False  
        self.actions = []
        self.start_time = 0
        self.playback_speed = 1.0
        self.continuous_playback = False
        self.custom_loops = 1  
        self.stop_event = threading.Event()
        
        self.hk_rec_text = "F8"
        self.hk_play_text = "F9"
        self.vk_rec = 0x77  
        self.vk_play = 0x78 
        
        self.keyboard_listener = None
        self.pressed_keys_track = set() 
        
        self.docs_folder = os.path.join(os.path.expanduser('~'), 'Documents', 'TaskMaster')
        if not os.path.exists(self.docs_folder): 
            os.makedirs(self.docs_folder)

# ==============================================================================
# BLOCO 10: CONSTRUÇÃO E RENDERIZAÇÃO DA INTERFACE GRÁFICA (UI)
# Monta os painéis visuais (frames), cria botões de ação rápidos, switches 
# de controle (Loop, Topo, Ignorar) e barras de status utilizando CustomTkinter.
# Ao final, dispara a thread paralela encarregada de monitorar as Hotkeys Globais.
# ==============================================================================
        self.toolbar = ctk.CTkFrame(self, height=40, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=15, pady=(10, 0))

        self.btn_folder = ctk.CTkButton(self.toolbar, text="📂 Pasta", width=85, height=28, command=self.open_folder)
        self.btn_folder.pack(side="left", padx=2)

        self.btn_import = ctk.CTkButton(self.toolbar, text="📥 Importar", width=85, height=28, command=self.load_manually)
        self.btn_import.pack(side="left", padx=2)

        self.btn_export = ctk.CTkButton(self.toolbar, text="📤 Exportar", width=85, height=28, command=self.save_manually)
        self.btn_export.pack(side="left", padx=2)

        self.switch_ignore_mouse = ctk.CTkSwitch(self.toolbar, text="Ignorar Mouse", command=self.toggle_ignore_mouse)
        self.switch_ignore_mouse.pack(side="right", padx=5)

        self.switch_top = ctk.CTkSwitch(self.toolbar, text="Sempre no Topo", command=self.toggle_top)
        self.switch_top.pack(side="right", padx=5)

        self.switch_loop = ctk.CTkSwitch(self.toolbar, text="Loop Infinito", command=self.toggle_loop)
        self.switch_loop.pack(side="right", padx=5)

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="x", padx=15, pady=10)

        self.btn_rec = ctk.CTkButton(self.main_frame, text=f"⚫ GRAVAR ({self.hk_rec_text})", width=140, height=45, 
                                     fg_color="#3a3a3a", hover_color="#555555", font=("Arial", 11, "bold"), command=self.toggle_recording)
        self.btn_rec.pack(side="left", padx=3)

        self.btn_play = ctk.CTkButton(self.main_frame, text=f"▶ REPRODUZIR ({self.hk_play_text})", width=140, height=45, 
                                      fg_color="#1f6aa5", hover_color="#2980b9", font=("Arial", 11, "bold"), command=self.toggle_playback)
        self.btn_play.pack(side="left", padx=3)

        self.btn_speed = ctk.CTkButton(self.main_frame, text="⚡ Vel: 1.0x", width=110, height=45, 
                                       fg_color="#2e7d32", hover_color="#388e3c", font=("Arial", 11, "bold"), command=self.change_speed)
        self.btn_speed.pack(side="left", padx=3)

        self.btn_loops = ctk.CTkButton(self.main_frame, text="🔄 Repetir: 1x", width=110, height=45,
                                       fg_color="#d35400", hover_color="#e67e22", font=("Arial", 11, "bold"), command=self.change_loops)
        self.btn_loops.pack(side="left", padx=3)

        self.btn_hotkeys = ctk.CTkButton(self.main_frame, text="⌨️ Atalhos", width=110, height=45, 
                                         fg_color="#5c3a21", hover_color="#704728", font=("Arial", 11, "bold"), command=self.setup_hotkeys)
        self.btn_hotkeys.pack(side="right", padx=3)

        self.status_bar = ctk.CTkLabel(self, text="Pronto (Modo Administrador Ativo).", anchor="w", font=("Arial", 11))
        self.status_bar.pack(fill="x", side="bottom", padx=20, pady=5)

        threading.Thread(target=self.global_hotkey_loop, daemon=True).start()

# ==============================================================================
# BLOCO 11: LOOP DE MONITORAMENTO GLOBAL DE HOTKEYS
# ==============================================================================
    def global_hotkey_loop(self):
        while True:
            if not self.is_changing_hotkeys:
                if ctypes.windll.user32.GetAsyncKeyState(self.vk_rec) & 0x8000:
                    self.after(0, self.toggle_recording)
                    time.sleep(0.4) 
                
                if ctypes.windll.user32.GetAsyncKeyState(self.vk_play) & 0x8000:
                    self.after(0, self.toggle_playback)
                    time.sleep(0.4)
                
            time.sleep(0.02)

# ==============================================================================
# BLOCO 12: SISTEMA DE CAPTURA E ISOLAMENTO DE NOVOS ATALHOS (HOTKEYS)
# ==============================================================================
    def setup_hotkeys(self):
        if self.is_recording or self.is_playing: return
        
        self.is_changing_hotkeys = True
        
        grabber = ctk.CTkToplevel(self)
        grabber.title("Capturando Atalhos")
        grabber.geometry("420x160")
        grabber.resizable(False, False)
        grabber.attributes('-topmost', True)
        grabber.grab_set()
        grabber.geometry(f"+{self.winfo_x() + 140}+{self.winfo_y() + 20}")

        lbl = ctk.CTkLabel(grabber, text="Pressione a tecla ou botão lateral do mouse\npara configurar a função: GRAVAR", font=("Arial", 12, "bold"))
        lbl.pack(pady=20)

        loop_control = {"running": True, "stage": "rec"}

        def wait_for_release(vk):
            while ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000:
                time.sleep(0.01)
            ctypes.windll.user32.GetAsyncKeyState(vk)

        def on_close_grabber():
            loop_control["running"] = False
            self.is_changing_hotkeys = False
            grabber.destroy()

        grabber.protocol("WM_DELETE_WINDOW", on_close_grabber)

        def mouse_hardware_blocker_thread():
            while loop_control["running"]:
                if loop_control["stage"] == "rec":
                    if ctypes.windll.user32.GetAsyncKeyState(0x05) & 0x8000:
                        self.vk_rec = 0x05
                        self.hk_rec_text = "MOUSE 4"
                        self.after(0, lambda: self.btn_rec.configure(text=f"⚫ GRAVAR ({self.hk_rec_text})"))
                        wait_for_release(0x05)
                        loop_control["stage"] = "play"
                        self.after(0, lambda: lbl.configure(text="Agora pressione a tecla ou botão lateral do mouse\npara configurar a função: REPRODUZIR"))
                    elif ctypes.windll.user32.GetAsyncKeyState(0x06) & 0x8000:
                        self.vk_rec = 0x06
                        self.hk_rec_text = "MOUSE 5"
                        self.after(0, lambda: self.btn_rec.configure(text=f"⚫ GRAVAR ({self.hk_rec_text})"))
                        wait_for_release(0x06)
                        loop_control["stage"] = "play"
                        self.after(0, lambda: lbl.configure(text="Agora pressione a tecla ou botão lateral do mouse\npara configurar a função: REPRODUZIR"))
                        
                elif loop_control["stage"] == "play":
                    if ctypes.windll.user32.GetAsyncKeyState(0x05) & 0x8000:
                        if self.vk_rec != 0x05:
                            self.vk_play = 0x05
                            self.hk_play_text = "MOUSE 4"
                            self.after(0, lambda: self.btn_play.configure(text=f"▶ REPRODUZIR ({self.hk_play_text})"))
                            wait_for_release(0x05)
                            loop_control["running"] = False
                            self.is_changing_hotkeys = False
                            self.after(0, grabber.destroy)
                    elif ctypes.windll.user32.GetAsyncKeyState(0x06) & 0x8000:
                        if self.vk_rec != 0x06:
                            self.vk_play = 0x06
                            self.hk_play_text = "MOUSE 5"
                            self.after(0, lambda: self.btn_play.configure(text=f"▶ REPRODUZIR ({self.hk_play_text})"))
                            wait_for_release(0x06)
                            loop_control["running"] = False
                            self.is_changing_hotkeys = False
                            self.after(0, grabber.destroy)
                time.sleep(0.01)

        def get_key_rec(event):
            key_name = event.keysym.lower()
            vk = TK_TO_VK.get(key_name, None)
            if vk:
                if loop_control["stage"] == "rec":
                    self.vk_rec = vk
                    self.hk_rec_text = key_name.upper()
                    self.btn_rec.configure(text=f"⚫ GRAVAR ({self.hk_rec_text})")
                    wait_for_release(vk)
                    loop_control["stage"] = "play"
                    lbl.configure(text="Agora pressione a tecla ou botão lateral do mouse\npara configurar a função: REPRODUZIR")
                elif loop_control["stage"] == "play" and vk != self.vk_rec:
                    self.vk_play = vk
                    self.hk_play_text = key_name.upper()
                    self.btn_play.configure(text=f"▶ REPRODUZIR ({self.hk_play_text})")
                    wait_for_release(vk)
                    loop_control["running"] = False
                    self.is_changing_hotkeys = False
                    grabber.destroy()

        grabber.bind("<Key>", get_key_rec)
        threading.Thread(target=mouse_hardware_blocker_thread, daemon=True).start()

# ==============================================================================
# BLOCO 13: BLOQUEIO DINÂMICO DOS ELEMENTOS DA INTERFACE (UI LOCK/UNLOCK)
# ==============================================================================
    def lock_ui(self, mode):
        state = "disabled" if mode in ["recording", "playing"] else "normal"
        self.btn_play.configure(state="disabled" if mode == "recording" else state)
        self.btn_rec.configure(state="disabled" if mode == "playing" else state)
        self.btn_speed.configure(state=state)
        self.btn_loops.configure(state=state)
        self.btn_folder.configure(state=state)
        self.btn_import.configure(state=state)
        self.btn_export.configure(state=state)
        self.btn_hotkeys.configure(state=state)
        self.switch_loop.configure(state=state)
        self.switch_ignore_mouse.configure(state=state)

# ==============================================================================
# BLOCO 14: ATUALIZADOR DA BARRA DE STATUS VISUAL
# ==============================================================================
    def update_status(self, text, color=None):
        self.after(0, lambda: self.status_bar.configure(text=text, text_color=color))

# ==============================================================================
# BLOCO 15: CONTROLES DE ESTADO VISUAIS (SWITCHES DE CONFIGURAÇÃO)
# ==============================================================================
    def toggle_top(self): self.attributes('-topmost', bool(self.switch_top.get()))
    def toggle_loop(self): self.continuous_playback = bool(self.switch_loop.get())
    def toggle_ignore_mouse(self): self.ignore_mouse_enabled = bool(self.switch_ignore_mouse.get())

# ==============================================================================
# BLOCO 16: JANELA E COORDENAÇÃO DE VELOCIDADE DE REPRODUÇÃO
# ==============================================================================
    def change_speed(self):
        if self.is_playing or self.is_recording: return
        speed_win = ctk.CTkToplevel(self)
        speed_win.title("Velocidade")
        speed_win.geometry("280x130")
        speed_win.resizable(False, False)
        speed_win.attributes('-topmost', True)
        speed_win.grab_set()
        speed_win.geometry(f"+{self.winfo_x() + 200}+{self.winfo_y() + 20}")

        lbl = ctk.CTkLabel(speed_win, text="Digite a velocidade (0.1 a 100.0):", font=("Arial", 11, "bold"))
        lbl.pack(pady=(15, 5))

        entry = ctk.CTkEntry(speed_win, width=120, justify="center")
        entry.insert(0, str(self.playback_speed))
        entry.pack(pady=5)

        def confirm_speed():
            try:
                self.playback_speed = max(0.1, min(100.0, float(entry.get())))
                self.btn_speed.configure(text=f"⚡ Vel: {self.playback_speed}x")
            except ValueError: pass
            speed_win.destroy()

        btn_ok = ctk.CTkButton(speed_win, text="Confirmar", width=80, command=confirm_speed)
        btn_ok.pack(pady=5)

# ==============================================================================
# BLOCO 17: JANELA DE SELEÇÃO DA QUANTIDADE DE REPETIÇÕES FINITAS
# ==============================================================================
    def change_loops(self):
        if self.is_playing or self.is_recording: return
        loop_win = ctk.CTkToplevel(self)
        loop_win.title("Repetições")
        loop_win.geometry("280x130")
        loop_win.resizable(False, False)
        loop_win.attributes('-topmost', True)
        loop_win.grab_set()
        loop_win.geometry(f"+{self.winfo_x() + 200}+{self.winfo_y() + 20}")

        lbl = ctk.CTkLabel(loop_win, text="Repetir o macro quantas vezes? (Inteiro):", font=("Arial", 11, "bold"))
        lbl.pack(pady=(15, 5))

        entry = ctk.CTkEntry(loop_win, width=120, justify="center")
        entry.insert(0, str(self.custom_loops))
        entry.pack(pady=5)

        def confirm_loops():
            try:
                val = int(entry.get())
                self.custom_loops = max(1, val) 
                self.btn_loops.configure(text=f"🔄 Repetir: {self.custom_loops}x")
            except ValueError: pass
            loop_win.destroy()

        btn_ok = ctk.CTkButton(loop_win, text="Confirmar", width=80, command=confirm_loops)
        btn_ok.pack(pady=5)

# ==============================================================================
# BLOCO 18: CHAVEADOR E DISPARADOR DO ESTADO DE GRAVAÇÃO
# ==============================================================================
    def toggle_recording(self):
        if self.is_playing or self.is_changing_hotkeys: return
        if not self.is_recording:
            threading.Thread(target=self.countdown, daemon=True).start()
        else:
            self.stop_recording()

# ==============================================================================
# BLOCO 19: CONTAGEM REGRESSIVA VISUAL DE PREPARAÇÃO
# ==============================================================================
    def countdown(self):
        self.lock_ui("recording")
        for i in range(3, 0, -1):
            if self.is_playing: return
            self.update_status(f"Gravando em {i}...", "#ff4d4d")
            time.sleep(1)
        self.start_recording()

# ==============================================================================
# BLOCO 20: ABRE OS ESCUTADORES (LISTENERS) DE PERIFÉRICOS
# ==============================================================================
    def start_recording(self):
        self.is_recording = True
        self.actions = []
        self.pressed_keys_track.clear()
        self.start_time = time.perf_counter() 
        self.after(0, lambda: self.btn_rec.configure(fg_color="#ff4d4d", text=f"⬛ PARAR ({self.hk_rec_text})"))
        self.update_status(f"Gravando!", "#ff4d4d")

        self.keyboard_listener = pynput_keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.keyboard_listener.start()

        if not self.ignore_mouse_enabled:
            threading.Thread(target=self.hardware_mouse_logger, daemon=True).start()

# ==============================================================================
# BLOCO 21: MONITOR FÍSICO DE HARDWARE DE MOUSE (COORDENADAS E CLIQUES)
# ==============================================================================
    def hardware_mouse_logger(self):
        VK_LBUTTON = 0x01
        VK_RBUTTON = 0x02
        
        state_left = ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON)
        state_right = ctypes.windll.user32.GetAsyncKeyState(VK_RBUTTON)
        
        last_pos = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(last_pos))
        
        while self.is_recording:
            if self.ignore_mouse_enabled: 
                break

            current_pos = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(current_pos))
            current_elapsed = time.perf_counter() - self.start_time
            
            if current_pos.x != last_pos.x or current_pos.y != last_pos.y:
                self.actions.append({'type': 'move', 'time': current_elapsed, 'x': current_pos.x, 'y': current_pos.y})
            
            last_pos = current_pos
            
            a = ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON)
            if a != state_left:
                state_left = a
                if not self.is_mouse_over_ui(current_pos.x, current_pos.y):
                    self.actions.append({'type': 'click', 'time': current_elapsed, 'button': 'left', 'pressed': bool(a & 0x8000)})
            
            b = ctypes.windll.user32.GetAsyncKeyState(VK_RBUTTON)
            if b != state_right:
                state_right = b
                if not self.is_mouse_over_ui(current_pos.x, current_pos.y):
                    self.actions.append({'type': 'click', 'time': current_elapsed, 'button': 'right', 'pressed': bool(b & 0x8000)})
                    
            time.sleep(0.002)

# ==============================================================================
# BLOCO 22: RECONHECEDOR DE FRONTEIRA DO MOUSE (MÁSCARA DE COORDENADAS)
# ==============================================================================
    def is_mouse_over_ui(self, x, y):
        x_min = self.winfo_rootx()
        y_min = self.winfo_rooty()
        x_max = x_min + self.winfo_width()
        y_max = y_min + self.winfo_height()
        return (x_min <= x <= x_max) and (y_min <= y <= y_max)

# ==============================================================================
# BLOCO 23: PARADA DA GRAVAÇÃO E PERSISTÊNCIA AUTOMÁTICA (AUTOSAVE)
# ==============================================================================
    def stop_recording(self):
        if not self.is_recording: return
        self.is_recording = False
        if self.keyboard_listener: self.keyboard_listener.stop()
        
        ctypes.windll.user32.keybd_event(0, 0, 0x0002, 0) 
        self.after(0, lambda: self.btn_rec.configure(fg_color="#3a3a3a", text=f"⚫ GRAVAR ({self.hk_rec_text})"))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.docs_folder, f'autosave_{timestamp}.rec')
        with open(filepath, 'wb') as f: pickle.dump(self.actions, f)
        self.lock_ui("unlock")
        self.update_status(f"Gravado! Ações computadas: {len(self.actions)}", "#2e7d32")

# ==============================================================================
# BLOCO 24: FUNÇÃO DE CAPTURA DE TECLA PRESSIONADA (FILTRO HÍBRIDO SELETIVO)
# Modificadores (Shift, Ctrl, Alt) filtram repetição contínua para evitar fantasmas
# de teclado magnético. Teclas normais mantêm repetição para permitir segurar a letra.
# ==============================================================================
    def on_press(self, key):
        if not self.is_recording: return
        vk = key.value.vk if hasattr(key, 'value') and hasattr(key.value, 'vk') else (key.vk if hasattr(key, 'vk') else None)
        if vk and vk not in [self.vk_rec, self.vk_play]: 
            
            if vk in [0x10, 0x11, 0x12]:
                if vk in self.pressed_keys_track: return
            
            self.pressed_keys_track.add(vk)
            self.actions.append({'type': 'press', 'time': time.perf_counter() - self.start_time, 'vk': vk})

# ==============================================================================
# BLOCO 25: FUNÇÃO DE CAPTURA DE TECLA SOLTA
# ==============================================================================
    def on_release(self, key):
        if not self.is_recording: return
        vk = key.value.vk if hasattr(key, 'value') and hasattr(key.value, 'vk') else (key.vk if hasattr(key, 'vk') else None)
        if vk and vk not in [self.vk_rec, self.vk_play]: 
            if vk in self.pressed_keys_track:
                self.pressed_keys_track.remove(vk)
            self.actions.append({'type': 'release', 'time': time.perf_counter() - self.start_time, 'vk': vk})

# ==============================================================================
# BLOCO 26: PREPARAÇÃO DO ENGINE DE REPRODUÇÃO E EXECUÇÃO (VERSÃO AMORTECIDA)
# ==============================================================================
    def toggle_playback(self):
        if self.is_recording or self.is_changing_hotkeys: return
        if not self.is_playing:
            if not self.actions: return
            self.is_playing = True
            self.stop_event.clear()
            self.lock_ui("playing")
            self.update_status("Reproduzindo...", "#1f6aa5")
            threading.Thread(target=self.playback_thread, daemon=True).start()
        else:
            self.is_playing = False
            self.stop_event.set()

    def playback_thread(self):
        loops_to_run = 99999999 if self.continuous_playback else self.custom_loops
        current_loop = 0
        
        modificadores_seguranca = [0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0x5B, 0x5C]
        
        while current_loop < loops_to_run and self.is_playing:
            if self.stop_event.is_set(): break
            
            playback_start = time.perf_counter()
            last_vk = None
            
            for action in self.actions:
                if self.stop_event.is_set() or not self.is_playing: break
                
                target_time = action['time'] / self.playback_speed
                while (time.perf_counter() - playback_start) < target_time:
                    if self.stop_event.is_set() or not self.is_playing: break
                    time.sleep(0.0005)
                
                if action['type'] == 'move':
                    send_mouse_hardware_absolute(action['x'], action['y'])
                
                elif action['type'] == 'click':
                    flags = 0
                    if action['button'] == 'left':
                        flags = MOUSEEVENTF_LEFTDOWN if action['pressed'] else MOUSEEVENTF_LEFTUP
                    elif action['button'] == 'right':
                        flags = MOUSEEVENTF_RIGHTDOWN if action['pressed'] else MOUSEEVENTF_RIGHTUP
                    
                    pos = wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(pos))
                    send_mouse_hardware_absolute(pos.x, pos.y, flags)
                    time.sleep(0.002)
                
                elif action['type'] in ['press', 'release']:
                    vk = action['vk']
                    pressed = (action['type'] == 'press')
                    
                    # Amortecedor de hardware: se for modificador (ex: Shift), estende o tempo de transição
                    if vk in [0x10, 0x11, 0x12]:
                        time.sleep(0.025)
                    elif vk == last_vk:
                        time.sleep(0.015)
                        
                    send_hardware_key(vk, pressed=pressed)
                    last_vk = vk
                    time.sleep(0.001) 
            
            current_loop += 1
            if self.continuous_playback:
                self.update_status(f"Reproduzindo (Loop infinito - Ciclo {current_loop})...", "#1f6aa5")
            else:
                self.update_status(f"Reproduzindo (Ciclo {current_loop}/{self.custom_loops})...", "#1f6aa5")
        
        # Garante o levantamento físico forçado de qualquer modificador ao finalizar
        for vk in modificadores_seguranca:
            send_hardware_key(vk, pressed=False)
            time.sleep(0.002)
                
        self.is_playing = False
        self.lock_ui("unlock")
        self.update_status("Pronto (Modo Administrador Ativo).")

# ==============================================================================
# BLOCO 27: SISTEMA DE GERENCIAMENTO DE ARQUIVOS (IO)
# ==============================================================================
    def open_folder(self):
        os.startfile(self.docs_folder)

    def save_manually(self):
        if not self.actions: return
        filepath = filedialog.asksaveasfilename(initialdir=self.docs_folder, title="Salvar Macro", 
                                                filetypes=[("TaskMaster Files", "*.rec")])
        if filepath:
            if not filepath.endswith('.rec'): filepath += '.rec'
            with open(filepath, 'wb') as f: pickle.dump(self.actions, f)
            self.update_status("Macro exportado com sucesso!", "#2e7d32")

    def load_manually(self):
        if self.is_recording or self.is_playing: return
        filepath = filedialog.askopenfilename(initialdir=self.docs_folder, title="Selecionar Macro", 
                                              filetypes=[("TaskMaster Files", "*.rec")])
        if filepath:
            with open(filepath, 'rb') as f:
                try:
                    self.actions = pickle.load(f)
                    self.update_status(f"Macro importado! Ações carregadas: {len(self.actions)}", "#2e7d32")
                except:
                    self.update_status("Erro ao carregar o arquivo.", "#ff4d4d")

if __name__ == "__main__":
    app = TaskMasterApp()
    app.mainloop()