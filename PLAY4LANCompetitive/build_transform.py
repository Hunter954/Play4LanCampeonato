from pathlib import Path

root = Path('upstream')

def edit(rel, replacements):
    p = root / rel
    s = p.read_text(encoding='utf-8')
    for old, new in replacements:
        if old not in s:
            print(f'AVISO: trecho não encontrado em {rel}: {old[:80]!r}')
        s = s.replace(old, new)
    p.write_text(s, encoding='utf-8')

# Identidade e comandos oficiais PLAY4LAN.
edit('MatchZy.cs', [
    ('public override string ModuleName => "MatchZy";', 'public override string ModuleName => "PLAY4LAN Competitive";'),
    ('public override string ModuleVersion => "0.8.15";', 'public override string ModuleVersion => "1.0.1";'),
    ('public override string ModuleAuthor => "WD- (https://github.com/shobhit-pathak/)";', 'public override string ModuleAuthor => "PLAY4LAN";'),
    ('public override string ModuleDescription => "A plugin for running and managing CS2 practice/pugs/scrims/matches!";', 'public override string ModuleDescription => "Motor competitivo oficial PLAY4LAN para campeonatos de CS2.";'),
    ('public string chatPrefix = $"[{ChatColors.Green}MatchZy{ChatColors.Default}]";', 'public string chatPrefix = $"[{ChatColors.Green}PLAY4LAN{ChatColors.Default}]";'),
    ('public string adminChatPrefix = $"[{ChatColors.Green}MatchZy Admin{ChatColors.Default}]";', 'public string adminChatPrefix = $"[{ChatColors.Green}PLAY4LAN ADMIN{ChatColors.Default}]";'),
    ('bool isPauseCommandForTactical = false;', 'bool isPauseCommandForTactical = false;\n\n        public Dictionary<int, HashSet<ulong>> play4lanTacticalVotes = new() { { 2, new HashSet<ulong>() }, { 3, new HashSet<ulong>() } };\n        public bool play4lanAllReadyAnnounced = false;'),
    ('Server.ExecuteCommand("execifexists MatchZy/config.cfg");', 'Server.ExecuteCommand("execifexists PLAY4LAN/config.cfg");'),
    ('{ ".ready", OnPlayerReady },\n                { ".r", OnPlayerReady },\n                { ".unready", OnPlayerUnReady },\n                { ".ur", OnPlayerUnReady },\n                { ".notready", OnPlayerUnReady },', '{ ".pronto", OnPlayerReady },\n                { ".naopronto", OnPlayerUnReady },'),
    ('{ ".stay", OnTeamStay },\n                { ".switch", OnTeamSwitch },\n                { ".swap", OnTeamSwitch },', '{ ".faca", OnPlay4LanStartKnife },\n                { ".ficar", OnTeamStay },\n                { ".trocar", OnTeamSwitch },'),
    ('{ ".tech", OnTechCommand },\n                { ".pause", OnPauseCommand },\n                { ".unpause", OnUnpauseCommand },\n                { ".tac", OnTacCommand },', '{ ".pause", OnPlay4LanTacticalPause },\n                { ".tac", OnPlay4LanTacticalPause },\n                { ".tec", OnPlay4LanTechnicalPause },\n                { ".voltar", OnPlay4LanResume },\n                { ".placar", OnPlay4LanScore },\n                { ".pausas", OnPlay4LanPauses },\n                { ".comandos", OnPlay4LanCommands },'),
    ('Console.WriteLine($"[{ModuleName} {ModuleVersion} LOADED] MatchZy by WD- (https://github.com/shobhit-pathak/)");', 'Console.WriteLine($"[{ModuleName} {ModuleVersion} CARREGADO] Motor competitivo PLAY4LAN pronto.");'),
])

# Comandos chat/console em português e retirada dos handlers antigos conflitantes.
edit('ConsoleCommands.cs', [
    ('[ConsoleCommand("css_ready", "Marks the player ready")]', '[ConsoleCommand("css_pronto", "Marca o jogador como pronto")]'),
    ('[ConsoleCommand("css_unready", "Marks the player unready")]\n        [ConsoleCommand("css_notready", "Marks the player unready")]', '[ConsoleCommand("css_naopronto", "Marca o jogador como não pronto")]'),
    ('[ConsoleCommand("css_stay", "Stays after knife round")]', '[ConsoleCommand("css_ficar", "Mantém o lado após o round faca")]'),
    ('[ConsoleCommand("css_switch", "Switch after knife round")]\n        [ConsoleCommand("css_swap", "Switch after knife round")]', '[ConsoleCommand("css_trocar", "Troca o lado após o round faca")]'),
    ('        [ConsoleCommand("css_tech", "Pause the match")]\n', ''),
    ('        [ConsoleCommand("css_pause", "Pause the match")]\n', ''),
    ('        [ConsoleCommand("css_unpause", "Unpause the match")]\n', ''),
    ('        [ConsoleCommand("css_tac", "Starts a tactical timeout for the requested team")]\n', ''),
])

# PLAY4LAN nunca inicia automaticamente quando todos digitam .pronto.
p = root / 'Utility.cs'
s = p.read_text(encoding='utf-8')
start = s.index('        private void CheckLiveRequired()')
end = s.index('        private void HandleMatchStart()', start)
new_check = '''        private void CheckLiveRequired()\n        {\n            if (!readyAvailable || matchStarted) return;\n            int ready = playerReadyStatus.Count(kv => kv.Value == true);\n            bool allReady;\n            if (isMatchSetup) allReady = IsTeamsReady() && IsSpectatorsReady();\n            else if (minimumReadyRequired == 0) allReady = ready >= connectedPlayers && connectedPlayers > 0;\n            else allReady = ready >= minimumReadyRequired;\n\n            if (allReady && !play4lanAllReadyAnnounced)\n            {\n                play4lanAllReadyAnnounced = true;\n                PrintToAllChat($"{ChatColors.Green}Todos os jogadores estão prontos.{ChatColors.Default} Aguardando o árbitro iniciar o round faca.");\n            }\n            else if (!allReady) play4lanAllReadyAnnounced = false;\n        }\n\n'''
s = s[:start] + new_check + s[end:]
for old, new in [
    ('public const string warmupCfgPath = "MatchZy/warmup.cfg";', 'public const string warmupCfgPath = "PLAY4LAN/warmup.cfg";'),
    ('public const string knifeCfgPath = "MatchZy/knife.cfg";', 'public const string knifeCfgPath = "PLAY4LAN/knife.cfg";'),
    ('public const string liveCfgPath = "MatchZy/live.cfg";', 'public const string liveCfgPath = "PLAY4LAN/live.cfg";'),
    ('public const string liveWingmanCfgPath = "MatchZy/live_wingman.cfg";', 'public const string liveWingmanCfgPath = "PLAY4LAN/live_wingman.cfg";'),
    ('string whitelistfileName = "MatchZy/whitelist.cfg";', 'string whitelistfileName = "PLAY4LAN/whitelist.cfg";'),
]:
    s = s.replace(old, new)
p.write_text(s, encoding='utf-8')

# Caminhos internos PLAY4LAN.
edit('DemoManagement.cs', [('public string demoPath = "MatchZy/";', 'public string demoPath = "PLAY4LAN/";')])
edit('SleepMode.cs', [('public const string sleepCfgPath = "MatchZy/sleep.cfg";', 'public const string sleepCfgPath = "PLAY4LAN/sleep.cfg";')])
edit('PracticeMode.cs', [
    ('public const string practiceCfgPath = "MatchZy/prac.cfg";', 'public const string practiceCfgPath = "PLAY4LAN/prac.cfg";'),
    ('public const string dryrunCfgPath = "MatchZy/dryrun.cfg";', 'public const string dryrunCfgPath = "PLAY4LAN/dryrun.cfg";'),
    ('"MatchZy/savednades.json"', '"PLAY4LAN/savednades.json"'),
])
edit('BackupManagement.cs', [
    ('matchzy_{liveMatchId}_{matchConfig.CurrentMapNumber}', 'play4lan_{liveMatchId}_{matchConfig.CurrentMapNumber}'),
    ('"MatchZyDataBackup"', '"PLAY4LANDataBackup"'),
    ('var pattern = $"matchzy_{matchID}_";', 'var pattern = $"play4lan_{matchID}_";'),
    ('[ConsoleCommand("matchzy_loadbackup",', '[ConsoleCommand("play4lan_loadbackup",'),
    ('[ConsoleCommand("matchzy_loadbackup_url",', '[ConsoleCommand("play4lan_loadbackup_url",'),
    ('[ConsoleCommand("matchzy_listbackups",', '[ConsoleCommand("play4lan_listbackups",'),
])

# Fonte adicional com as regras PLAY4LAN.
(root / 'Play4LanCommands.cs').write_text(r'''using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Utils;

namespace MatchZy;

public partial class MatchZy
{
    [ConsoleCommand("css_faca", "Inicia manualmente o round faca PLAY4LAN")]
    public void OnPlay4LanStartKnife(CCSPlayerController? player, CommandInfo? command)
    {
        if (!IsPlayerAdmin(player, "css_faca", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (matchStarted) { ReplyToUserCommand(player, "A partida já foi iniciada."); return; }
        if (isPractice) { ReplyToUserCommand(player, "Não é possível iniciar o round faca no modo de treino."); return; }
        isKnifeRequired = true;
        PrintToAllChat($"{ChatColors.Green}Árbitro iniciou o ROUND FACA.{ChatColors.Default}");
        HandleMatchStart();
    }

    [ConsoleCommand("css_pause", "Solicita pausa tática PLAY4LAN")]
    [ConsoleCommand("css_tac", "Solicita pausa tática PLAY4LAN")]
    public void OnPlay4LanTacticalPause(CCSPlayerController? player, CommandInfo? command)
    {
        if (player == null) { Server.PrintToConsole("[PLAY4LAN] Pausa tática deve ser solicitada pelos jogadores."); return; }
        if (!matchStarted || !isMatchLive) { ReplyToUserCommand(player, "A pausa tática só pode ser solicitada com a partida ao vivo."); return; }
        if (isPaused) { ReplyToUserCommand(player, "A partida já está pausada."); return; }
        if (IsHalfTimePhase() || IsPostGamePhase() || IsTacticalTimeoutActive()) { ReplyToUserCommand(player, "Não é possível solicitar pausa tática neste momento."); return; }
        if (player.TeamNum != 2 && player.TeamNum != 3) return;

        var rules = Utilities.FindAllEntitiesByDesignerName<CCSGameRulesProxy>("cs_gamerules").FirstOrDefault()?.GameRules;
        if (rules == null) { ReplyToUserCommand(player, "Não foi possível consultar as pausas da partida."); return; }
        int remaining = player.TeamNum == 2 ? rules.TerroristTimeOuts : rules.CTTimeOuts;
        Team team = player.TeamNum == 2 ? reverseTeamSides["TERRORIST"] : reverseTeamSides["CT"];
        if (remaining <= 0) { ReplyToUserCommand(player, $"{team.teamName} não possui mais pausas táticas."); return; }

        var votes = play4lanTacticalVotes[player.TeamNum];
        if (!votes.Add(player.SteamID)) { ReplyToUserCommand(player, $"Seu voto já foi registrado. {team.teamName}: {votes.Count}/3."); return; }
        PrintToAllChat($"{ChatColors.Green}{team.teamName}{ChatColors.Default} — {votes.Count}/3 solicitações de pausa tática.");
        if (votes.Count < 3) return;

        PrintToAllChat($"{ChatColors.Green}{team.teamName}{ChatColors.Default} — 3/3. PAUSA TÁTICA SOLICITADA.");
        Server.ExecuteCommand(player.TeamNum == 2 ? "timeout_terrorist_start" : "timeout_ct_start");
        votes.Clear();
    }

    [ConsoleCommand("css_tec", "Solicita pausa técnica PLAY4LAN")]
    public void OnPlay4LanTechnicalPause(CCSPlayerController? player, CommandInfo? command)
    {
        if (player == null || (player.TeamNum != 2 && player.TeamNum != 3)) return;
        if (!matchStarted || !isMatchLive) { ReplyToUserCommand(player, "A pausa técnica só pode ser solicitada durante uma partida ao vivo."); return; }
        if (isPaused || IsHalfTimePhase() || IsPostGamePhase() || IsTacticalTimeoutActive()) { ReplyToUserCommand(player, "Não é possível solicitar pausa técnica neste momento."); return; }
        Team team = player.TeamNum == 2 ? reverseTeamSides["TERRORIST"] : reverseTeamSides["CT"];
        unpauseData["pauseTeam"] = "Admin";
        PrintToAllChat($"{ChatColors.Green}{team.teamName}{ChatColors.Default} SOLICITOU PAUSA TÉCNICA.");
        PrintToAllChat("Aguardando o árbitro autorizar a retomada.");
        SetMatchPausedFlags();
    }

    [ConsoleCommand("css_voltar", "Retoma uma partida pausada - árbitro")]
    public void OnPlay4LanResume(CCSPlayerController? player, CommandInfo? command)
    {
        if (!IsPlayerAdmin(player, "css_voltar", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (!matchStarted || !isPaused) { ReplyToUserCommand(player, "Não há pausa técnica para retomar."); return; }
        PrintToAllChat($"{ChatColors.Green}Árbitro autorizou a retomada da partida.{ChatColors.Default}");
        UnpauseMatch();
    }

    [ConsoleCommand("css_placar", "Mostra o placar atual")]
    public void OnPlay4LanScore(CCSPlayerController? player, CommandInfo? command)
    {
        (int a, int b) = GetTeamsScore();
        if (player == null) { Server.PrintToConsole($"[PLAY4LAN] {matchzyTeam1.teamName} {a} x {b} {matchzyTeam2.teamName}"); return; }
        PrintToPlayerChat(player, $"{ChatColors.Green}{matchzyTeam1.teamName}{ChatColors.Default} {a} x {b} {ChatColors.Green}{matchzyTeam2.teamName}{ChatColors.Default}");
    }

    [ConsoleCommand("css_pausas", "Mostra as pausas táticas restantes")]
    public void OnPlay4LanPauses(CCSPlayerController? player, CommandInfo? command)
    {
        var rules = Utilities.FindAllEntitiesByDesignerName<CCSGameRulesProxy>("cs_gamerules").FirstOrDefault()?.GameRules;
        if (rules == null) return;
        string t = reverseTeamSides["TERRORIST"].teamName, ct = reverseTeamSides["CT"].teamName;
        if (player == null) { Server.PrintToConsole($"[PLAY4LAN] {t}: {rules.TerroristTimeOuts}/4 | {ct}: {rules.CTTimeOuts}/4"); return; }
        PrintToPlayerChat(player, $"{t}: {rules.TerroristTimeOuts}/4 pausas táticas restantes.");
        PrintToPlayerChat(player, $"{ct}: {rules.CTTimeOuts}/4 pausas táticas restantes.");
    }

    [ConsoleCommand("css_comandos", "Mostra os comandos oficiais PLAY4LAN")]
    public void OnPlay4LanCommands(CCSPlayerController? player, CommandInfo? command)
    {
        if (player == null) { Server.PrintToConsole("[PLAY4LAN] .pronto .naopronto .ficar .trocar .pause/.tac .tec .placar .pausas | árbitro: .faca .voltar"); return; }
        PrintToPlayerChat(player, $"{ChatColors.Green}COMANDOS PLAY4LAN{ChatColors.Default}");
        PrintToPlayerChat(player, ".pronto / .naopronto — status de pronto");
        PrintToPlayerChat(player, ".ficar / .trocar — escolha após o round faca");
        PrintToPlayerChat(player, ".pause / .tac — pausa tática, exige 3 jogadores do mesmo time");
        PrintToPlayerChat(player, ".tec — pausa técnica sem tempo limite");
        PrintToPlayerChat(player, ".placar — placar atual | .pausas — pausas restantes");
        if (IsPlayerAdmin(player)) PrintToPlayerChat(player, ".faca — iniciar faca | .voltar — retomar pausa técnica");
    }
}
''', encoding='utf-8')

# Assembly próprio e CounterStrikeSharp igual ao servidor atual.
csproj = root / 'MatchZy.csproj'
s = csproj.read_text(encoding='utf-8')
s = s.replace('<TargetFramework>net8.0</TargetFramework>', '<TargetFramework>net8.0</TargetFramework>\n    <AssemblyName>PLAY4LANCompetitive</AssemblyName>')
s = s.replace('Version="1.0.342"', 'Version="1.0.373"')
csproj.write_text(s, encoding='utf-8')

# Configuração: reaproveita a base estável e renomeia para PLAY4LAN.
src_cfg = root / 'cfg' / 'MatchZy'
dst_cfg = root / 'cfg' / 'PLAY4LAN'
src_cfg.rename(dst_cfg)
for p in dst_cfg.rglob('*'):
    if p.is_file():
        try:
            t = p.read_text(encoding='utf-8').replace('MatchZy/', 'PLAY4LAN/')
            p.write_text(t, encoding='utf-8')
        except UnicodeDecodeError:
            pass

config = dst_cfg / 'config.cfg'
config.write_text(config.read_text(encoding='utf-8') + '''\n\n// PLAY4LAN\nmatchzy_minimum_ready_required 0\nmatchzy_demo_recording_enabled true\nmatchzy_demo_path PLAY4LAN/\nmatchzy_demo_name_format "PLAY4LAN_{TIME}_{MATCH_ID}_{MAP}_{TEAM1}_vs_{TEAM2}"\nmatchzy_stop_command_available false\nmatchzy_use_pause_command_for_tactical_pause false\nmatchzy_enable_tech_pause true\nmatchzy_tech_pause_duration -1\nmatchzy_max_tech_pauses_allowed 999\nmatchzy_pause_after_restore true\nmatchzy_chat_prefix [{Green}PLAY4LAN{Default}]\nmatchzy_admin_chat_prefix [{Green}PLAY4LAN ADMIN{Default}]\nmatchzy_show_credits_on_match_start false\nmatchzy_hostname_format "PLAY4LAN SERVER 01 | {TEAM1} vs {TEAM2}"\n''', encoding='utf-8')

for name in ['live_override.cfg', 'live_wingman_override.cfg']:
    q = dst_cfg / name
    q.write_text(q.read_text(encoding='utf-8') + '''\nmp_team_timeout_max 4\nmp_team_timeout_time 30\nmp_freezetime 20\nmp_team_timeout_ot_max 0\nmp_team_timeout_ot_add_each 0\nmp_overtime_enable 1\nmp_overtime_maxrounds 6\nmp_overtime_startmoney 10000\nmp_backup_round_auto 1\nmp_backup_restore_load_autopause 1\n''', encoding='utf-8')

warmup = dst_cfg / 'warmup.cfg'
warmup.write_text(warmup.read_text(encoding='utf-8') + '\nmp_warmup_pausetimer 1\nmp_warmuptime 9999\n', encoding='utf-8')

# Interface inteira em português: usa pt-BR como idioma para todos os clientes.
pt = root / 'lang' / 'pt-BR.json'
t = pt.read_text(encoding='utf-8')
t = t.replace('MatchZy', 'PLAY4LAN').replace('.ready', '.pronto').replace('.unready', '.naopronto').replace('.stay', '.ficar').replace('.switch', '.trocar').replace('.tech', '.tec').replace('.unpause', '.voltar')
pt.write_text(t, encoding='utf-8')
for q in (root / 'lang').glob('*.json'):
    q.write_text(t, encoding='utf-8')

print('Transformação PLAY4LAN concluída.')