from pathlib import Path
import re

root = Path('upstream')

# Corrige detalhes que variam no fonte 0.8.15 e deixa somente os comandos PLAY4LAN no chat.
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public string adminChatPrefix = $"[{ChatColors.Red}ADMIN{ChatColors.Default}]";', 'public string adminChatPrefix = $"[{ChatColors.Green}PLAY4LAN ADMIN{ChatColors.Default}]";')
start = s.index('            commandActions = new Dictionary<string, Action<CCSPlayerController?, CommandInfo?>> {')
end = s.index('            RegisterEventHandler<EventPlayerConnectFull>', start)
command_map = '''            commandActions = new Dictionary<string, Action<CCSPlayerController?, CommandInfo?>> {
                { ".pronto", OnPlayerReady },
                { ".naopronto", OnPlayerUnReady },
                { ".faca", OnPlay4LanStartKnife },
                { ".ficar", OnTeamStay },
                { ".trocar", OnTeamSwitch },
                { ".pause", OnPlay4LanTacticalPause },
                { ".tac", OnPlay4LanTacticalPause },
                { ".tec", OnPlay4LanTechnicalPause },
                { ".voltar", OnPlay4LanResume },
                { ".placar", OnPlay4LanScore },
                { ".pausas", OnPlay4LanPauses },
                { ".comandos", OnPlay4LanCommands }
            };

'''
s = s[:start] + command_map + s[end:]
p.write_text(s, encoding='utf-8')

# CounterStrikeSharp 1.0.373 é net10.0.
p = root / 'MatchZy.csproj'
s = p.read_text(encoding='utf-8')
s = s.replace('<TargetFramework>net8.0</TargetFramework>', '<TargetFramework>net10.0</TargetFramework>')
p.write_text(s, encoding='utf-8')

# Garante que handlers antigos não registrem os mesmos comandos do PLAY4LAN.
p = root / 'ConsoleCommands.cs'
s = p.read_text(encoding='utf-8')
for attr in [
    '[ConsoleCommand("css_tech", "Pause the match")]\n',
    '[ConsoleCommand("css_pause", "Pause the match")]\n',
    '[ConsoleCommand("css_unpause", "Unpause the match")]\n',
    '[ConsoleCommand("css_tac", "Starts a tactical timeout for the requested team")]\n',
]:
    s = s.replace('        ' + attr, '')
p.write_text(s, encoding='utf-8')

print('Correções finais PLAY4LAN aplicadas.')