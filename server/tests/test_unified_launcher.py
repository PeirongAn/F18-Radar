import copy
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('unified_launcher', ROOT / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_control_writes_strategy_before_launch_and_passes_directory(tmp_path, monkeypatch):
    script = tmp_path / '调控 启动.cmd'
    script.touch()
    config = copy.deepcopy(launcher.DEFAULT_CONFIG)
    config['tendency'] = 'over_trust'
    def spawn(command, **kwargs):
        saved = json.loads((tmp_path / 'trust_control_v1.json').read_text(encoding='utf-8'))
        assert saved == config
        assert kwargs['env']['F18_RADAR_CONFIG_DIR'] == str(tmp_path)
        assert kwargs['cwd'] == tmp_path
        assert str(script) in command
        return Mock(pid=123)
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    assert launcher.launch_script(str(script), 'control', str(tmp_path), config,
                                  tmp_path / 'run.log').pid == 123


def test_normal_does_not_write_trust_config(tmp_path, monkeypatch):
    script = tmp_path / 'normal.ps1'
    script.touch()
    spawn = Mock()
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    launcher.launch_script(str(script), 'normal', 'not-a-directory', {}, tmp_path / 'run.log')
    assert not (tmp_path / 'trust_control_v1.json').exists()
    assert spawn.call_args.args[0][-1] == str(script)


def test_invalid_configuration_never_starts_script(tmp_path, monkeypatch):
    script = tmp_path / 'control.exe'
    script.touch()
    spawn = Mock()
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    with pytest.raises(ValueError):
        launcher.launch_script(str(script), 'control', str(tmp_path), {}, tmp_path / 'run.log')
    spawn.assert_not_called()


@pytest.mark.parametrize('name', ['missing.cmd', 'bad.txt', 'bad%PATH%.cmd'])
def test_rejects_invalid_script(tmp_path, name):
    path = tmp_path / name
    if name != 'missing.cmd':
        path.touch()
    with pytest.raises(ValueError):
        launcher.script_command(str(path))


def test_window_switch_preserves_both_drafts_and_hides_normal_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'SETTINGS', tmp_path / 'launcher_settings.json')
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    app = launcher.Launcher()
    app.withdraw()
    try:
        app.mode.set('control')
        app.show_mode()
        app.evidence.set(True)
        app.reliability.set(False)
        app.state.set('过信任')
        app.switch_state()
        app.reliability.set(True)
        app.state.set('欠信任')
        app.switch_state()
        assert app.evidence.get() is True
        assert app.reliability.get() is False
        app.directory.set(str(tmp_path))
        for mode, roles in app.scripts.items():
            for role, variable in roles.items():
                variable.set(str(tmp_path / f'{mode}-{role}.cmd'))
        assert app.save()
        settings = json.loads(launcher.SETTINGS.read_text(encoding='utf-8'))
        for mode, roles in app.scripts.items():
            for role, variable in roles.items():
                assert settings[f'{mode}_{role}_script'] == variable.get()
        app.load_settings()
        saved = json.loads((tmp_path / 'trust_control_v1.json').read_text(encoding='utf-8'))
        assert saved['policies']['over_trust']['show_reliability'] is True
        assert set(launcher.STATES) == {'欠信任', '过信任'}
        assert saved['policies']['normal'] == launcher.DEFAULT_CONFIG['policies']['normal']
        app.deiconify()
        app.update()
        assert app.start_button.winfo_ismapped()
        assert app.script_frames['control'].winfo_ismapped()
        assert not app.script_frames['normal'].winfo_ismapped()
        assert app.preview_box.winfo_rooty() + app.preview_box.winfo_height() <= app.footer.winfo_rooty()
    finally:
        app.destroy()


@pytest.mark.parametrize('server_code,frontend_fails', [(None, False), (2, False), (None, True)])
def test_pair_start_order_and_partial_failure(tmp_path, monkeypatch, server_code, frontend_fails):
    from types import SimpleNamespace
    from functools import partial
    scripts = {}
    for role in ('server', 'frontend'):
        path = tmp_path / f'{role}.cmd'
        path.touch()
        scripts[role] = Mock(get=Mock(return_value=str(path)))
    server = Mock(poll=Mock(return_value=server_code))
    frontend = Mock(poll=Mock(return_value=None))
    spawn = Mock(side_effect=[server, OSError('frontend failed') if frontend_fails else frontend])
    monkeypatch.setattr(launcher, 'launch_script', spawn)
    monkeypatch.setattr(launcher, 'ServerJob', Mock())
    app = SimpleNamespace(server_job=None, starting=False, processes={}, mode=Mock(get=Mock(return_value='control')),
                          scripts={'control': scripts}, save=Mock(return_value=True),
                          directory=Mock(get=Mock(return_value=str(tmp_path))),
                          config_data=copy.deepcopy(launcher.DEFAULT_CONFIG), status=Mock(), after=Mock(),
                          check_process=Mock())
    app.start_frontend = partial(launcher.Launcher.start_frontend, app)
    launcher.Launcher.start(app)
    assert spawn.call_args.args[0] == scripts['server'].get()
    assert spawn.call_count == 1
    app.after.call_args.args[1]()
    assert app.starting is False
    if server_code == 2:
        assert spawn.call_count == 1
        assert '未启动前端' in app.status.set.call_args.args[0]
    else:
        assert spawn.call_count == 2
        assert spawn.call_args.args[0] == scripts['frontend'].get()
        assert spawn.call_args.kwargs['write_config'] is False
        if frontend_fails:
            assert app.processes['Server'] is server
            assert 'Server 可能仍在运行' in app.status.set.call_args.args[0]


def test_missing_frontend_prevents_server_start(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'server.cmd'
    path.touch()
    spawn = Mock()
    monkeypatch.setattr(launcher, 'launch_script', spawn)
    app = SimpleNamespace(server_job=None, starting=False, processes={}, mode=Mock(get=Mock(return_value='normal')),
                          scripts={'normal': {'server': Mock(get=Mock(return_value=str(path))),
                                              'frontend': Mock(get=Mock(return_value=''))}}, status=Mock())
    launcher.Launcher.start(app)
    spawn.assert_not_called()
    assert '前端' in app.status.set.call_args.args[0]


def test_close_cleans_job_before_destroying_window():
    from types import SimpleNamespace
    actions = []
    job = Mock(close=Mock(side_effect=lambda: actions.append('stop')))
    app = SimpleNamespace(server_job=job, destroy=lambda: actions.append('destroy'), status=Mock())
    launcher.Launcher.close_window(app)
    assert actions == ['stop', 'destroy']


def test_job_stops_orphaned_server_descendant_only(tmp_path):
    import ctypes
    from ctypes import wintypes as w
    import sys
    import time
    from launcher_process import ServerJob
    job = ServerJob()
    pid_file = tmp_path / 'child.pid'
    code = ('import subprocess,sys,pathlib; '
            'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
            f'pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))')
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    handle = None
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes, api.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    api.WaitForSingleObject.argtypes, api.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
    api.CloseHandle.argtypes = [w.HANDLE]
    try:
        worker = job.spawn([sys.executable, '-c', code], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        assert worker.wait(timeout=10) == 0
        assert pid_file.exists()
        handle = api.OpenProcess(0x100000, False, int(pid_file.read_text()))
        assert handle
        assert job.active()  # Entry script has exited, but the actual Server is alive.
        job.close()
        assert api.WaitForSingleObject(handle, 5000) == 0
        assert unrelated.poll() is None
    finally:
        job.close()
        if handle:
            api.CloseHandle(handle)
        unrelated.terminate()
        unrelated.wait(timeout=5)
