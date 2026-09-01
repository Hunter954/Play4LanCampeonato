from pathlib import Path

root = Path('upstream')


def replace_method(path: Path, signature: str, replacement: str):
    s = path.read_text(encoding='utf-8')
    start = s.index(signature)
    brace = s.index('{', start)
    depth = 0
    end = None
    for i in range(brace, len(s)):
        if s[i] == '{':
            depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f'Nao foi possivel localizar o fim de {signature}')
    s = s[:start] + replacement + s[end:]
    path.write_text(s, encoding='utf-8')

# Versao 1.0.5 + alias .espera.
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public override string ModuleVersion => "1.0.4";', 'public override string ModuleVersion => "1.0.5";')
s = s.replace('{ ".naopronto", OnPlayerUnReady },', '{ ".espera", OnPlayerUnReady },')
s = s.replace('Use .naopronto para liberar a troca de lado.', 'Use .espera para liberar a troca de lado.')
# Estado do modo de testes. Comeca ligado nesta build para teste solo.
needle = '        public bool play4lanAllReadyAnnounced = false;'
if 'play4lanTestMode' not in s:
    s = s.replace(needle, needle + '\n        public bool play4lanTestMode = true;')
p.write_text(s, encoding='utf-8')

# Comando console/chat oficial .espera.
p = root / 'ConsoleCommands.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('[ConsoleCommand("css_naopronto", "Marca o jogador como não pronto")]', '[ConsoleCommand("css_espera", "Retira o pronto e volta o jogador para espera")]')
p.write_text(s, encoding='utf-8')

# Atualiza textos de ajuda.
for name in ['Play4LanCommands.cs']:
    p = root / name
    s = p.read_text(encoding='utf-8')
    s = s.replace('.naopronto', '.espera')
    p.write_text(s, encoding='utf-8')

# No modo teste, um unico jogador pronto libera a partida.
p = root / 'Play4LanReadyVisual.cs'
replace_method(p, 'private bool IsPlay4LanFullReady()', r'''private bool IsPlay4LanFullReady()
    {
        if (play4lanTestMode)
        {
            foreach (var item in playerReadyStatus)
                if (item.Value) return true;
            return false;
        }

        var (tPlayers, tReady) = GetTeamPlayerCount((int)CsTeam.Terrorist, false);
        var (ctPlayers, ctReady) = GetTeamPlayerCount((int)CsTeam.CounterTerrorist, false);
        return tPlayers == 5 && ctPlayers == 5 && tReady == 5 && ctReady == 5;
    }''')

# .pronto inicia automaticamente a partida quando modo teste estiver ligado.
p = root / 'Utility.cs'
replace_method(p, 'private void CheckLiveRequired()', r'''private void CheckLiveRequired()
        {
            if (!readyAvailable || matchStarted) return;

            if (play4lanTestMode)
            {
                int ready = playerReadyStatus.Count(kv => kv.Value == true);
                if (ready >= 1)
                {
                    PrintToAllChat($"{ChatColors.Green}MODO TESTE PLAY4LAN: 1 jogador pronto. Iniciando partida automaticamente...{ChatColors.Default}");
                    isKnifeRequired = false;
                    HandleMatchStart();
                }
                return;
            }

            bool allReady = IsPlay4LanFullReady();
            if (allReady && !play4lanAllReadyAnnounced)
            {
                play4lanAllReadyAnnounced = true;
                PrintToAllChat($"{ChatColors.Green}════════ 10/10 JOGADORES PRONTOS ════════{ChatColors.Default}");
                PrintToAllChat("Partida liberada. Aguardando o árbitro usar .faca");
            }
            else if (!allReady)
            {
                play4lanAllReadyAnnounced = false;
            }
        }''')

# Painel de status deixa claro quando o servidor esta em teste solo.
p = root / 'Play4LanReadyVisual.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('PrintToAllChat($"{ChatColors.Green}━━━━━━━━ {teamName} ━━━━━━━━{ChatColors.Default}");', 'PrintToAllChat($"{ChatColors.Green}━━━━━━━━ {teamName} ━━━━━━━━{ChatColors.Default}");\n        if (play4lanTestMode) PrintToAllChat($"{ChatColors.Green}MODO TESTE: 1 jogador pronto inicia a partida.{ChatColors.Default}");', 1)
p.write_text(s, encoding='utf-8')

# Comando administrativo para ligar/desligar o modo teste sem recompilar.
(root / 'Play4LanTestMode.cs').write_text(r'''using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Core.Attributes.Registration;
using CounterStrikeSharp.API.Modules.Commands;

namespace MatchZy;

public partial class MatchZy
{
    [ConsoleCommand("play4lan_test_mode", "PLAY4LAN: 1 liga teste solo, 0 volta para 5x5")]
    public void OnPlay4LanTestMode(CCSPlayerController? player, CommandInfo command)
    {
        if (player != null && !IsPlayerAdmin(player, "play4lan_test_mode", "@css/config"))
        {
            SendPlayerNotAdminMessage(player);
            return;
        }

        string value = command.ArgByIndex(1);
        if (value != "0" && value != "1")
        {
            command.ReplyToCommand($"[PLAY4LAN] Modo teste: {(play4lanTestMode ? "LIGADO" : "DESLIGADO")}. Uso: play4lan_test_mode 1 ou 0");
            return;
        }

        play4lanTestMode = value == "1";
        play4lanAllReadyAnnounced = false;
        command.ReplyToCommand(play4lanTestMode
            ? "[PLAY4LAN] MODO TESTE LIGADO: 1 jogador com .pronto inicia automaticamente."
            : "[PLAY4LAN] MODO TESTE DESLIGADO: regra oficial 5/5 x 5/5 restaurada.");
    }
}
''', encoding='utf-8')

print('PLAY4LAN v1.0.5 aplicado: .espera + modo teste solo configuravel.')
