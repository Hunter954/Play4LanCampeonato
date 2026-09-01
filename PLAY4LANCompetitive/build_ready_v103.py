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

# Versao 1.0.3
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public override string ModuleVersion => "1.0.2";', 'public override string ModuleVersion => "1.0.3";')
p.write_text(s, encoding='utf-8')

# Remove completamente o aviso/timer legado do MatchZy no warmup.
p = root / 'Utility.cs'
replace_method(p, 'private void SendUnreadyPlayersMessage()', '''private void SendUnreadyPlayersMessage()\n        {\n            // PLAY4LAN v1.0.3: mensagens antigas de minimumReadyRequired desativadas.\n            return;\n        }''')
s = p.read_text(encoding='utf-8')
s = s.replace('            unreadyPlayerMessageTimer ??= AddTimer(chatTimerDelay, SendUnreadyPlayersMessage, TimerFlags.REPEAT);\n', '')
p.write_text(s, encoding='utf-8')

# Reescreve a camada visual: ao marcar pronto, mostra somente a equipe do jogador.
p = root / 'Play4LanReadyVisual.cs'
s = p.read_text(encoding='utf-8')
insert_marker = '    private void PrintPlay4LanReadyBoard()\n'
idx = s.index(insert_marker)
team_method = r'''    private void PrintPlay4LanTeamReadyBoard(int teamNum)
    {
        var (players, ready) = GetTeamPlayerCount(teamNum, false);
        string teamName = Play4LanTeamName(teamNum);
        PrintToAllChat($"{ChatColors.Green}━━━━━━━━ {teamName} ━━━━━━━━{ChatColors.Default}");
        PrintToAllChat($"[{Play4LanReadyBar(ready)}] {ready}/5 prontos • {players}/5 no servidor");
        PrintToAllChat($"✓ Prontos: {Play4LanReadyNames(teamNum)}");
        if (players < 5)
            PrintToAllChat($"Aguardando jogadores: {players}/5");
        else if (ready < 5)
            PrintToAllChat($"Aguardando .pronto: {ready}/5");
        else
            PrintToAllChat($"{ChatColors.Green}✓ {teamName} COMPLETO — 5/5 PRONTOS{ChatColors.Default}");
    }

    private void PrintPlay4LanTeamReadyBoardToPlayer(CCSPlayerController player)
    {
        int teamNum = player.TeamNum;
        if (teamNum != (int)CsTeam.Terrorist && teamNum != (int)CsTeam.CounterTerrorist)
        {
            ReplyToUserCommand(player, "Entre em uma das equipes para consultar o status.");
            return;
        }

        var (players, ready) = GetTeamPlayerCount(teamNum, false);
        string teamName = Play4LanTeamName(teamNum);
        PrintToPlayerChat(player, $"{ChatColors.Green}━━━━━━━━ {teamName} ━━━━━━━━{ChatColors.Default}");
        PrintToPlayerChat(player, $"[{Play4LanReadyBar(ready)}] {ready}/5 prontos • {players}/5 no servidor");
        PrintToPlayerChat(player, $"✓ Prontos: {Play4LanReadyNames(teamNum)}");
    }

'''
s = s[:idx] + team_method + s[idx:]
p.write_text(s, encoding='utf-8')

replace_method(p, 'public void OnPlay4LanReadyStatus(CCSPlayerController? player, CommandInfo? command)', r'''public void OnPlay4LanReadyStatus(CCSPlayerController? player, CommandInfo? command)
    {
        if (player == null)
        {
            PrintPlay4LanReadyBoard();
            return;
        }
        PrintPlay4LanTeamReadyBoardToPlayer(player);
    }''')

# Ao dar .pronto, trava o lado escolhido e mostra apenas o status daquela equipe.
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
            play4lanReadyLockedTeam[id] = player.TeamNum;
            var (_, readyCount) = GetTeamPlayerCount(player.TeamNum, false);
            PrintToAllChat($"{ChatColors.Green}✓ {player.PlayerName}{ChatColors.Default} está PRONTO — {teamName} {readyCount}/5");
            PrintPlay4LanTeamReadyBoard(player.TeamNum);
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
            play4lanReadyLockedTeam.Remove(id);
            string teamName = Play4LanTeamName(player.TeamNum);
            var (_, readyCount) = GetTeamPlayerCount(player.TeamNum, false);
            PrintToAllChat($"{player.PlayerName} retirou o PRONTO — {teamName} {readyCount}/5");
            PrintPlay4LanTeamReadyBoard(player.TeamNum);
            play4lanAllReadyAnnounced = false;
            CheckLiveRequired();
            HandleClanTags();
        }''')

# Adiciona mapa de lado travado para jogadores prontos.
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
needle = '        private Dictionary<int, CCSPlayerController> playerData = new Dictionary<int, CCSPlayerController>();\n'
if 'play4lanReadyLockedTeam' not in s:
    s = s.replace(needle, needle + '        private Dictionary<int, int> play4lanReadyLockedTeam = new Dictionary<int, int>();\n')

# Substitui listener jointeam para bloquear M/troca de lado apos .pronto.
old = '''            AddCommandListener("jointeam", (player, info) =>
            {
                if ((isMatchSetup || isVeto) && player != null && player.IsValid) {
                    if (int.TryParse(info.ArgByIndex(1), out int joiningTeam)) {
                        int playerTeam = (int)GetPlayerTeam(player);
                        if (joiningTeam != playerTeam) {
                            return HookResult.Stop;
                        }
                    }
                }
                return HookResult.Continue;
            });'''
new = '''            AddCommandListener("jointeam", (player, info) =>
            {
                if (player != null && player.IsValid && player.UserId.HasValue)
                {
                    int id = player.UserId.Value;
                    if (play4lanReadyLockedTeam.TryGetValue(id, out int lockedTeam))
                    {
                        if (int.TryParse(info.ArgByIndex(1), out int joiningTeam) && joiningTeam != lockedTeam)
                        {
                            string teamName = Play4LanTeamName(lockedTeam);
                            ReplyToUserCommand(player, $"Você já confirmou presença pelo {teamName}. Use .naopronto para liberar a troca de lado.");
                            return HookResult.Stop;
                        }
                    }
                }

                if ((isMatchSetup || isVeto) && player != null && player.IsValid) {
                    if (int.TryParse(info.ArgByIndex(1), out int joiningTeam)) {
                        int playerTeam = (int)GetPlayerTeam(player);
                        if (joiningTeam != playerTeam) {
                            return HookResult.Stop;
                        }
                    }
                }
                return HookResult.Continue;
            });'''
if old not in s:
    raise RuntimeError('Listener jointeam original nao encontrado para patch v1.0.3')
s = s.replace(old, new)
p.write_text(s, encoding='utf-8')

print('PLAY4LAN v1.0.3 aplicado: sem spam legado, status por equipe e lado travado apos .pronto.')
