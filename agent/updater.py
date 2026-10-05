"""Versão do CS2 instalado, checagem de atualização na Valve e atualização via SteamCMD."""
import pathlib
import re
import subprocess
import threading
import time

import requests

VALVE_CHECK = 'https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/'
CHECK_EVERY = 300  # 5 min
METAMOD_LINE = '\t\t\tGame\tcsgo/addons/metamod\n'
# Um SteamCMD por vez: duas instâncias simultâneas brigam pelo mesmo cache.
STEAMCMD_LOCK = threading.Lock()


def read_steam_inf(install_dir):
    path = pathlib.Path(install_dir) / 'game' / 'csgo' / 'steam.inf'
    data = {}
    try:
        for line in path.read_text(encoding='utf8', errors='ignore').splitlines():
            if '=' in line:
                k, _, v = line.partition('='); data[k.strip()] = v.strip()
    except OSError:
        pass
    return data


def installed_version(install_dir):
    return read_steam_inf(install_dir).get('PatchVersion')


def check_valve(version):
    """Pergunta à Valve se a versão está atualizada. Retorna dict com up_to_date/required."""
    r = requests.get(VALVE_CHECK, params={'appid': 730, 'version': version, 'format': 'json'}, timeout=10)
    r.raise_for_status()
    resp = r.json().get('response') or {}
    if not resp.get('success'):
        raise RuntimeError(resp.get('error') or 'Resposta inválida da Valve')
    required = None
    m = re.search(r'(\d+\.\d+\.\d+\.\d+)', resp.get('message') or '')
    if m: required = m.group(1)
    return {'up_to_date': bool(resp.get('up_to_date')), 'required': required or (version if resp.get('up_to_date') else None)}


def ensure_metamod(install_dir):
    """Atualizações do CS2 regravam o gameinfo.gi e removem a linha do Metamod. Recoloca se faltar."""
    path = pathlib.Path(install_dir) / 'game' / 'csgo' / 'gameinfo.gi'
    if not path.exists() or not (pathlib.Path(install_dir) / 'game' / 'csgo' / 'addons' / 'metamod').exists():
        return False
    text = path.read_text(encoding='utf8', errors='ignore')
    if 'csgo/addons/metamod' in text:
        return False
    lines = text.splitlines(keepends=True)
    in_paths = False
    for i, line in enumerate(lines):
        if 'SearchPaths' in line: in_paths = True
        if in_paths and re.match(r'^\s*Game\s+csgo\s*$', line):
            lines.insert(i, METAMOD_LINE)
            path.write_text(''.join(lines), encoding='utf8')
            return True
    return False


def run_steamcmd(steamcmd, install_dir, log, timeout=3600):
    """Roda app_update 730 validate. `log` recebe cada linha de saída."""
    cmd = [steamcmd, '+force_install_dir', str(pathlib.Path(install_dir).resolve()), '+login', 'anonymous',
           '+app_update', '730', 'validate', '+quit']
    with STEAMCMD_LOCK:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='ignore',
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        started = time.time(); ok = False
        for line in proc.stdout:
            line = line.strip()
            if not line: continue
            log(line)
            if "Success! App '730' fully installed" in line or "Success! App '730' already up to date" in line: ok = True
            if time.time() - started > timeout:
                proc.kill(); log('Tempo limite do SteamCMD excedido.'); return False
        proc.wait()
        return ok or proc.returncode == 0
