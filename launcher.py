"""Local launcher; no server or browser is required to edit startup settings."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, ttk
from launcher_process import ServerJob

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'server'))
from services.trust_tendency import DEFAULT_CONFIG, TrustTendencySource

SETTINGS = ROOT / 'launcher_settings.json'
HIGHLIGHTS = {'无': 'none', '观测信息区': 'observation', '可靠性信息区': 'reliability'}
STATES = {'欠信任': 'under_trust', '过信任': 'over_trust'}


def write_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def script_command(value):
    path = Path(value.strip()).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise ValueError('请选择存在的启动脚本，路径必须是绝对路径。')
    suffix = path.suffix.lower()
    if suffix in ('.cmd', '.bat'):
        # cmd performs expansion even inside quotes. Reject expansion/control syntax.
        if any(char in str(path) for char in '%!^&|<>"\r\n'):
            raise ValueError('批处理脚本路径不能包含 % ! ^ & | < > 或引号，请改用普通目录名。')
        command = f'"{os.environ.get("COMSPEC", "C:/Windows/System32/cmd.exe")}" /d /s /c ""{path}""'
    elif suffix == '.ps1':
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(path)]
    elif suffix == '.exe':
        command = [str(path)]
    else:
        raise ValueError('支持 .cmd、.bat、.ps1 和 .exe 文件。')
    return path, command


def launch_script(script, mode, config_dir, config, log_path, write_config=True, job=None):
    path, command = script_command(script)
    env = os.environ.copy()
    if mode == 'control':
        directory = Path(config_dir).expanduser()
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError('请选择已存在的调控配置目录。')
        if write_config:
            TrustTendencySource(directory / 'trust_control_v1.json').save_config(config)
        env['F18_RADAR_CONFIG_DIR'] = str(directory)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with log_path.open('ab') as output:
        kwargs = dict(cwd=path.parent, env=env, stdout=output, stderr=output, startupinfo=startup,
                      creationflags=subprocess.CREATE_NO_WINDOW)
        if job is not None:
            return job.spawn(command, **kwargs)
        return subprocess.Popen(command, stdin=subprocess.DEVNULL, **kwargs)


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('统一启动与信任调控配置')
        self.geometry('850x920')
        self.minsize(800, 900)
        self.configure(bg='#eef2f5')
        self.config_data = copy.deepcopy(DEFAULT_CONFIG)
        self.current_state = 'under_trust'
        self.processes = {}
        self.server_job = None
        self.protocol('WM_DELETE_WINDOW', self.close_window)
        self.starting = False
        self.saved_settings = {}
        self.mode = tk.StringVar(value='normal')
        self.scripts = {mode: {role: tk.StringVar() for role in ('server', 'frontend')}
                        for mode in ('normal', 'control')}
        self.directory = tk.StringVar(value=str(ROOT / 'public'))
        self.state = tk.StringVar(value='欠信任')
        self.evidence = tk.BooleanVar()
        self.reliability = tk.BooleanVar()
        self.highlight = tk.StringVar(value='无')
        self.status = tk.StringVar(value='先选择对应版本的启动脚本。')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('TFrame', background='#eef2f5')
        style.configure('TLabel', background='#eef2f5')
        style.configure('TLabelframe', background='#eef2f5')
        style.configure('TLabelframe.Label', background='#eef2f5', font=('Microsoft YaHei UI', 11, 'bold'))
        style.configure('TButton', padding=(12, 7))
        body = ttk.Frame(self, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='实验系统启动', font=('Microsoft YaHei UI', 22, 'bold')).pack(anchor='w')
        ttk.Label(body, text='选择运行版本，为欠信任与过信任配置显示策略。').pack(anchor='w', pady=(5, 16))
        modes = ttk.Frame(body)
        modes.pack(fill='x')
        for label, value in [('正常模式', 'normal'), ('信任调控模式', 'control')]:
            ttk.Radiobutton(modes, text=label, value=value, variable=self.mode,
                            command=self.show_mode).pack(side='left', padx=(0, 24))
        scripts = ttk.LabelFrame(body, text='启动脚本', padding=12)
        scripts.pack(fill='x', pady=14)
        self.script_frames = {}
        for mode in ('normal', 'control'):
            frame = ttk.Frame(scripts)
            self.script_frames[mode] = frame
            self.path_row(frame, 'Server 端', self.scripts[mode]['server'])
            self.path_row(frame, '前端', self.scripts[mode]['frontend'])
        self.script_hint = ttk.Label(scripts, text='先启动 Server，再启动前端；不代表服务已就绪。')
        self.script_hint.pack(anchor='w')
        ttk.Label(scripts, text='支持 CMD / BAT / PowerShell / EXE；以脚本所在目录运行。').pack(anchor='w', pady=(5, 0))
        self.control_frame = ttk.Frame(body)
        self.path_row(self.control_frame, '配置目录', self.directory, directory=True)
        row = ttk.Frame(self.control_frame)
        row.pack(fill='x', pady=10)
        ttk.Label(row, text='信任倾向').pack(side='left', padx=(0, 12))
        combo = ttk.Combobox(row, textvariable=self.state, values=list(STATES), state='readonly', width=12)
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', self.switch_state)
        contents = ttk.LabelFrame(self.control_frame, text='信息内容调控 · 显示什么', padding=10)
        contents.pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(contents, text='显示补充观测依据', variable=self.evidence,
                        command=self.preview).pack(anchor='w')
        ttk.Checkbutton(contents, text='显示可靠性说明', variable=self.reliability,
                        command=self.preview).pack(anchor='w', pady=(6, 0))
        form = ttk.LabelFrame(self.control_frame, text='呈现形式调控 · 怎么显示', padding=10)
        form.pack(fill='x')
        ttk.Label(form, text='高亮区域').pack(side='left', padx=(0, 12))
        combo = ttk.Combobox(form, textvariable=self.highlight, values=list(HIGHLIGHTS), state='readonly')
        combo.pack(side='left')
        combo.bind('<<ComboboxSelected>>', lambda _: self.preview())
        self.preview_box = tk.Label(self.control_frame, anchor='w', justify='left', padx=16, pady=12,
                                    font=('Microsoft YaHei UI', 10), wraplength=650)
        self.preview_box.pack(fill='x', pady=12)
        self.normal_hint = ttk.Label(body, text='正常模式启动正常版 Server 和前端，无需填写调控策略。')
        self.footer = ttk.Frame(body)
        self.footer.pack(side='bottom', fill='x')
        ttk.Label(self.footer, textvariable=self.status, wraplength=720).pack(anchor='w', pady=8)
        actions = ttk.Frame(self.footer)
        actions.pack(fill='x')
        self.start_button = ttk.Button(actions, text='启动系统', command=self.start)
        self.start_button.pack(side='right')
        ttk.Button(actions, text='保存配置', command=self.save).pack(side='right', padx=8)
        ttk.Button(actions, text='关闭', command=self.close_window).pack(side='right')
        self.load_settings()
        self.load_policy()
        self.show_mode()

    def path_row(self, parent, label, variable, directory=False):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=label, width=9).pack(side='left')
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True, padx=8)
        def browse():
            value = (filedialog.askdirectory(parent=self) if directory else
                     filedialog.askopenfilename(parent=self, filetypes=[('启动文件', '*.cmd *.bat *.ps1 *.exe')]))
            if value:
                variable.set(value)
        ttk.Button(row, text='浏览…', command=browse).pack(side='left')

    def load_settings(self):
        try:
            if SETTINGS.exists():
                data = json.loads(SETTINGS.read_text(encoding='utf-8'))
                self.saved_settings = data
                for mode, roles in self.scripts.items():
                    for role, variable in roles.items():
                        variable.set(data.get(f'{mode}_{role}_script', ''))
                if 'normal_script' in data or 'control_script' in data:
                    self.status.set('旧版总入口路径已保留，请分别选择 Server 和前端脚本。')
                self.directory.set(data.get('config_dir', str(ROOT / 'public')))
                self.mode.set('control' if data.get('mode') == 'control' else 'normal')
            path = Path(self.directory.get()) / 'trust_control_v1.json'
            if path.exists():
                self.config_data = TrustTendencySource(path).read_config()
            self.current_state = self.config_data['tendency'] if self.config_data['tendency'] in STATES.values() else 'under_trust'
            self.state.set(next(k for k, v in STATES.items() if v == self.current_state))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self.status.set(f'配置读取失败，已保留默认草稿：{error}')

    def store_policy(self):
        self.config_data['policies'][self.current_state] = {
            'show_evidence': self.evidence.get(), 'show_reliability': self.reliability.get(),
            'highlight': HIGHLIGHTS[self.highlight.get()]}

    def load_policy(self):
        policy = self.config_data['policies'][self.current_state]
        self.evidence.set(policy['show_evidence'])
        self.reliability.set(policy['show_reliability'])
        self.highlight.set(next(k for k, v in HIGHLIGHTS.items() if v == policy['highlight']))
        self.preview()

    def switch_state(self, _=None):
        self.store_policy()
        self.current_state = STATES[self.state.get()]
        self.load_policy()

    def preview(self):
        content = self.evidence.get() or self.reliability.get()
        form = self.highlight.get() != '无'
        kind = '联合调控' if content and form else '内容调控' if content else '形式调控' if form else '基础显示'
        lines = [f'策略类型：{kind}  ·  效果示意', '基础观测信息 / AI 推荐结果']
        if self.evidence.get():
            lines.append('补充观测依据：展示当前任务的真实候选字段对比')
        if self.reliability.get():
            lines.append('系统局限：AI建议可能出错，请结合当前观测核验')
        lines.append(f'高亮：{self.highlight.get()}（高亮不自动增加内容）')
        colors = {'无': ('#e0e7ec', '#263b49'), '观测信息区': ('#0b2930', '#b9f5ff'),
                  '可靠性信息区': ('#302411', '#ffda91')}
        background, foreground = colors[self.highlight.get()]
        self.preview_box.configure(text='\n'.join(lines), bg=background, fg=foreground)

    def show_mode(self):
        for frame in self.script_frames.values():
            frame.pack_forget()
        self.script_frames[self.mode.get()].pack(fill='x', before=self.script_hint)
        self.control_frame.pack_forget()
        self.normal_hint.pack_forget()
        if self.mode.get() == 'control':
            self.control_frame.pack(fill='x')
            self.start_button.configure(text='保存配置并启动')
        else:
            self.normal_hint.pack(anchor='w', pady=12)
            self.start_button.configure(text='启动系统')

    def save(self):
        try:
            self.store_policy()
            self.config_data['tendency'] = self.current_state
            # Kept internally for the current backend schema, never offered as a strategy.
            self.config_data['policies']['normal'] = copy.deepcopy(DEFAULT_CONFIG['policies']['normal'])
            if self.mode.get() == 'control':
                directory = Path(self.directory.get()).expanduser()
                if not directory.is_absolute() or not directory.is_dir():
                    raise ValueError('请选择已存在的调控配置目录。')
                TrustTendencySource(directory / 'trust_control_v1.json').save_config(self.config_data)
            settings = {**self.saved_settings, 'mode': self.mode.get(), 'config_dir': self.directory.get()}
            for mode, roles in self.scripts.items():
                for role, variable in roles.items():
                    settings[f'{mode}_{role}_script'] = variable.get()
            write_json(SETTINGS, settings)
            self.saved_settings = settings
            self.status.set('配置已保存。启动时将使用所选脚本。')
            return True
        except (OSError, ValueError) as error:
            self.status.set(f'保存失败，草稿已保留：{error}')
            return False

    def start(self):
        try:
            if self.server_job is not None and self.server_job.active():
                self.status.set('本窗口启动的 Server 仍在运行，请先关闭系统，避免重复启动。')
                return
        except OSError as error:
            self.status.set(f'无法检查 Server 进程状态：{error}')
            return
        if self.starting or any(p.poll() is None for p in self.processes.values()):
            self.status.set('Server 或前端启动进程仍在运行，请先停止已启动的系统，避免重复启动。')
            return
        mode = self.mode.get()
        scripts = {role: variable.get() for role, variable in self.scripts[mode].items()}
        try:
            for role, script in scripts.items():
                try:
                    script_command(script)
                except ValueError as error:
                    raise ValueError(f'{"Server" if role == "server" else "前端"}：{error}') from error
            if not self.save():
                return
            directory, config = self.directory.get(), copy.deepcopy(self.config_data)
            self.processes = {}
            if self.server_job is None:
                self.server_job = ServerJob()
            self.processes['Server'] = launch_script(scripts['server'], mode, directory, config,
                                                      ROOT / 'launcher-server.log', job=self.server_job)
            self.starting = True
            self.status.set('已创建 Server 启动进程，接下来启动前端。')
            self.after(1200, lambda: self.start_frontend(scripts['frontend'], mode, directory, config))
        except (OSError, ValueError) as error:
            self.status.set(f'启动失败：{error}')

    def start_frontend(self, script, mode, directory, config):
        try:
            code = self.processes['Server'].poll()
            if code not in (None, 0):
                self.status.set(f'Server 脚本失败（退出码 {code}），未启动前端。查看 launcher-server.log。')
                return
            self.processes['前端'] = launch_script(script, mode, directory, config,
                                                  ROOT / 'launcher-frontend.log', write_config=False)
            self.check_process()
        except (OSError, ValueError) as error:
            self.status.set(f'前端启动失败：{error}；Server 可能仍在运行，请检查后再重试。')
        finally:
            self.starting = False

    def check_process(self):
        states = {role: process.poll() for role, process in self.processes.items()}
        labels = [f'{role}：' + ('启动进程运行中' if code is None else
                  '脚本已退出（0）' if code == 0 else f'失败（{code}）') for role, code in states.items()]
        self.status.set('；'.join(labels) + '。日志：launcher-server.log / launcher-frontend.log')
        if any(code is None for code in states.values()):
            self.after(1500, self.check_process)

    def close_window(self):
        try:
            if self.server_job is not None:
                self.server_job.close()
                self.server_job = None
        except OSError as error:
            self.status.set(f'Server 清理失败，窗口暂不关闭：{error}')
            return
        self.destroy()


if __name__ == '__main__':
    Launcher().mainloop()
