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


# v1.0.2
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public override string ModuleVersion => "1.0.1";', 'public override string ModuleVersion => "1.0.2";')
s = s.replace(
    '                { ".pausas", OnPlay4LanPauses },\n                { ".comandos", OnPlay4LanCommands }',
    '                { ".pausas", OnPlay4LanPauses },\n                { ".status", OnPlay4LanReadyStatus },\n                { ".prontos", OnPlay4LanReadyStatus },\n                { ".comandos", OnPlay4LanCommands }'
)
p.write_text(s, encoding='utf-8')

# Regra fixa PLAY4LAN: 5 jogadores e 5 prontos por equipe. Sem force-ready.
p = root / 'ReadySystem.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public bool allowForceReady = true;', 'public bool allowForceReady = false;')
s = s.replace(
    'if (playerCount == readyCount && playerCount >= minPlayers)',
    'if ((team == (int)CsTeam.Terrorist || team == (int)CsTeam.CounterTerrorist) ? (playerCount == 5 && readyCount == 5) : (playerCount == readyCount && playerCount >= minPlayers))'
)
s = s.replace(
    'if (team == (int)CsTeam.CounterTerrorist || team == (int)CsTeam.Terrorist) return matchConfig.PlayersPerTeam;',
    'if (team == (int)CsTeam.CounterTerrorist || team == (int)CsTeam.Terrorist) return 5;'
)
s = s.replace(
    'if (team == (int)CsTeam.CounterTerrorist || team == (int)CsTeam.Terrorist) return matchConfig.MinPlayersToReady;',
    'if (team == (int)CsTeam.CounterTerrorist || team == (int)CsTeam.Terrorist) return 5;'
)
p.write_text(s, encoding='utf-8')

# Interface visual de prontidao.
(root / 'Play4LanReadyVisual.cs').write_text(r'''using System;
using System.Collections.Generic;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Core.Attributes.Registration;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Utils;

namespace MatchZy;

public partial class MatchZy
{
    private string Play4LanTeamName(int teamNum)
    {
        if (teamNum == (int)CsTeam.Terrorist && reverseTeamSides.ContainsKey("TERRORIST"))
            return reverseTeamSides["TERRORIST"].teamName;
        if (teamNum == (int)CsTeam.CounterTerrorist && reverseTeamSides.ContainsKey("CT"))
            return reverseTeamSides["CT"].teamName;
        return teamNum == (int)CsTeam.Terrorist ? "TIME TR" : "TIME CT";
    }

    private string Play4LanReadyBar(int ready)
    {
        ready = Math.Clamp(ready, 0, 5);
        return new string('●', ready) + new string('○', 5 - ready);
    }

    private string Play4LanReadyNames(int teamNum)
    {
        var names = new List<string>();
        foreach (var key in playerData.Keys)
        {
            if (!playerData[key].IsValid || playerData[key].TeamNum != teamNum) continue;
            if (playerReadyStatus.TryGetValue(key, out bool ready) && ready)
                names.Add(playerData[key].PlayerName);
        }
        return names.Count == 0 ? "ninguém" : string.Join(", ", names);
    }

    private bool IsPlay4LanFullReady()
    {
        var (tPlayers, tReady) = GetTeamPlayerCount((int)CsTeam.Terrorist, false);
        var (ctPlayers, ctReady) = GetTeamPlayerCount((int)CsTeam.CounterTerrorist, false);
        return tPlayers == 5 && ctPlayers == 5 && tReady == 5 && ctReady == 5;
    }

    private void PrintPlay4LanReadyBoard()
    {
        var (tPlayers, tReady) = GetTeamPlayerCount((int)CsTeam.Terrorist, false);
        var (ctPlayers, ctReady) = GetTeamPlayerCount((int)CsTeam.CounterTerrorist, false);
        string tName = Play4LanTeamName((int)CsTeam.Terrorist);
        string ctName = Play4LanTeamName((int)CsTeam.CounterTerrorist);

        PrintToAllChat($"{ChatColors.Green}━━━━━━━━ STATUS DE PRONTIDÃO ━━━━━━━━{ChatColors.Default}");
        PrintToAllChat($"{ChatColors.Green}{tName}{ChatColors.Default} [{Play4LanReadyBar(tReady)}] {tReady}/5 prontos • {tPlayers}/5 no servidor");
        PrintToAllChat($"✓ Prontos: {Play4LanReadyNames((int)CsTeam.Terrorist)}");
        PrintToAllChat($"{ChatColors.Green}{ctName}{ChatColors.Default} [{Play4LanReadyBar(ctReady)}] {ctReady}/5 prontos • {ctPlayers}/5 no servidor");
        PrintToAllChat($"✓ Prontos: {Play4LanReadyNames((int)CsTeam.CounterTerrorist)}");

        if (tPlayers < 5 || ctPlayers < 5)
        {
            PrintToAllChat($"Aguardando jogadores: {tName} {tPlayers}/5 • {ctName} {ctPlayers}/5");
        }
        else if (tReady < 5 || ctReady < 5)
        {
            PrintToAllChat($"Aguardando .pronto: {tName} {tReady}/5 • {ctName} {ctReady}/5");
        }
        else
        {
            PrintToAllChat($"{ChatColors.Green}✓ TODOS PRONTOS — 5/5 x 5/5{ChatColors.Default}");
            PrintToAllChat("Aguardando o árbitro iniciar o ROUND FACA com .faca");
        }
    }

    [ConsoleCommand("css_status", "Mostra o status de prontidão PLAY4LAN")]
    [ConsoleCommand("css_prontos", "Mostra o status de prontidão PLAY4LAN")]
    public void OnPlay4LanReadyStatus(CCSPlayerController? player, CommandInfo? command)
    {
        PrintPlay4LanReadyBoard();
    }
}
''', encoding='utf-8')

# Troca o comportamento de .pronto e .naopronto, mantendo os atributos css_pronto/css_naopronto.
p = root / 'ConsoleCommands.cs'
replace_method(p, 'public void OnPlayerReady(CCSPlayerController? player, CommandInfo? command)', r'''public void OnPlayerReady(CCSPlayerController? player, CommandInfo? command)
        {
            if (player == null) return;
            if (!readyAvailable || matchStarted) return;
            if (player.TeamNum != (int)CsTeam.Terrorist && player.TeamNum != (int)CsTeam.CounterTerrorist)
            {
                ReplyToUserCommand(player, "Entre em uma das equipes para marcar .pronto.");
                return;
            }
            if (!player.UserId.HasValue) return;

            int id = player.UserId.Value;
            if (!playerReadyStatus.ContainsKey(id)) playerReadyStatus[id] = false;
            string teamName = Play4LanTeamName(player.TeamNum);

            if (playerReadyStatus[id])
            {
                ReplyToUserCommand(player, "Você já está PRONTO.");
                return;
            }

            playerReadyStatus[id] = true;
            var (_, readyCount) = GetTeamPlayerCount(player.TeamNum, false);
            PrintToAllChat($"{ChatColors.Green}✓ {player.PlayerName}{ChatColors.Default} está PRONTO — {teamName} {readyCount}/5");
            PrintPlay4LanReadyBoard();
            CheckLiveRequired();
            HandleClanTags();
        }''')

replace_method(p, 'public void OnPlayerUnReady(CCSPlayerController? player, CommandInfo? command)', r'''public void OnPlayerUnReady(CCSPlayerController? player, CommandInfo? command)
        {
            if (player == null) return;
            if (!readyAvailable || matchStarted) return;
            if (player.TeamNum != (int)CsTeam.Terrorist && player.TeamNum != (int)CsTeam.CounterTerrorist) return;
            if (!player.UserId.HasValue) return;

            int id = player.UserId.Value;
            if (!playerReadyStatus.ContainsKey(id) || !playerReadyStatus[id])
            {
                ReplyToUserCommand(player, "Você ainda não marcou .pronto.");
                return;
            }

            playerReadyStatus[id] = false;
            string teamName = Play4LanTeamName(player.TeamNum);
            var (_, readyCount) = GetTeamPlayerCount(player.TeamNum, false);
            PrintToAllChat($"{player.PlayerName} retirou o PRONTO — {teamName} {readyCount}/5");
            play4lanAllReadyAnnounced = false;
            PrintPlay4LanReadyBoard();
            CheckLiveRequired();
            HandleClanTags();
        }''')

# CheckLiveRequired: nunca inicia sozinho; só reconhece 5/5 x 5/5.
p = root / 'Utility.cs'
replace_method(p, 'private void CheckLiveRequired()', r'''private void CheckLiveRequired()
        {
            if (!readyAvailable || matchStarted) return;
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

# .faca só funciona com exatamente 5 conectados e prontos de cada lado.
p = root / 'Play4LanCommands.cs'
replace_method(p, 'public void OnPlay4LanStartKnife(CCSPlayerController? player, CommandInfo? command)', r'''public void OnPlay4LanStartKnife(CCSPlayerController? player, CommandInfo? command)
    {
        if (!IsPlayerAdmin(player, "css_faca", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (matchStarted) { ReplyToUserCommand(player, "A partida já foi iniciada."); return; }
        if (isPractice) { ReplyToUserCommand(player, "Não é possível iniciar o round faca no modo de treino."); return; }

        if (!IsPlay4LanFullReady())
        {
            ReplyToUserCommand(player, "ROUND FACA BLOQUEADO: são necessários 5 jogadores conectados e 5/5 prontos em cada equipe.");
            PrintPlay4LanReadyBoard();
            return;
        }

        isKnifeRequired = true;
        PrintToAllChat($"{ChatColors.Green}✓ CHECK-IN COMPLETO — 5/5 x 5/5{ChatColors.Default}");
        PrintToAllChat($"{ChatColors.Green}Árbitro iniciou o ROUND FACA.{ChatColors.Default}");
        HandleMatchStart();
    }''')

# Atualiza ajuda visual.
s = p.read_text(encoding='utf-8')
s = s.replace(
    '"[PLAY4LAN] .pronto .naopronto .ficar .trocar .pause/.tac .tec .placar .pausas | árbitro: .faca .voltar"',
    '"[PLAY4LAN] .pronto .naopronto .status/.prontos .ficar .trocar .pause/.tac .tec .placar .pausas | árbitro: .faca .voltar"'
)
s = s.replace(
    '".pronto .naopronto | .ficar .trocar | .pause/.tac (3 votos) | .tec | .placar | .pausas"',
    '".pronto .naopronto | .status/.prontos | .ficar .trocar | .pause/.tac (3 votos) | .tec | .placar | .pausas"'
)
p.write_text(s, encoding='utf-8')

print('PLAY4LAN v1.0.2: check-in 5v5 e painel visual de prontos aplicados.')
