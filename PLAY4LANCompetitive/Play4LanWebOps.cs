using System.Text.Json;
using System.Text.RegularExpressions;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Core.Attributes.Registration;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Events;
using CounterStrikeSharp.API.Modules.Utils;

namespace MatchZy;

public partial class MatchZy
{
    private sealed class P4LPlayerState
    {
        public int userid { get; set; }
        public ulong steam_id64 { get; set; }
        public string name { get; set; } = "";
        public string team { get; set; } = "SPEC";
        public string team_name { get; set; } = "ESPECTADOR";
        public bool ready { get; set; }
        public int ping { get; set; }
        public bool alive { get; set; }
        public int health { get; set; }
        public int armor { get; set; }
        public int money { get; set; }
        public int kills { get; set; }
        public int deaths { get; set; }
        public int assists { get; set; }
        public int damage { get; set; }
        public string weapon { get; set; } = "";
    }

    private sealed class P4LChatItem
    {
        public long seq { get; set; }
        public long ts { get; set; }
        public int userid { get; set; }
        public ulong steam_id64 { get; set; }
        public string name { get; set; } = "";
        public string team { get; set; } = "SPEC";
        public bool team_only { get; set; }
        public string text { get; set; } = "";
    }

    private sealed class P4LBackupItem
    {
        public string file { get; set; } = "";
        public int round { get; set; }
        public long modified_unix { get; set; }
    }

    private sealed class P4LServerState
    {
        public string map { get; set; } = "";
        public string phase { get; set; } = "AGUARDANDO";
        public bool paused { get; set; }
        public bool test_mode { get; set; }
        public int team1_score { get; set; }
        public int team2_score { get; set; }
        public List<P4LPlayerState> players { get; set; } = new();
        public List<P4LChatItem> chat { get; set; } = new();
        public List<P4LBackupItem> backups { get; set; } = new();
    }

    private readonly List<P4LChatItem> play4lanWebChat = new();
    private long play4lanWebChatSeq;

    private string P4LPhase()
    {
        if (isKnifeRound) return "FACA";
        if (isSideSelectionPhase) return "ESCOLHA_LADO";
        if (isMatchLive) return isPaused ? "PAUSADO" : "LIVE";
        if (isWarmup) return "AQUECIMENTO";
        if (isPractice) return "TREINO";
        return matchStarted ? "PARTIDA" : "AGUARDANDO";
    }

    [GameEventHandler]
    public HookResult OnPlay4LanWebChat(EventPlayerChat @event, GameEventInfo info)
    {
        if (!playerData.TryGetValue(@event.Userid, out var p) || p == null || !p.IsValid) return HookResult.Continue;
        string side = p.TeamNum == 2 ? "TR" : p.TeamNum == 3 ? "CT" : "SPEC";
        play4lanWebChat.Add(new P4LChatItem {
            seq = ++play4lanWebChatSeq,
            ts = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
            userid = @event.Userid,
            steam_id64 = p.SteamID,
            name = p.PlayerName,
            team = side,
            team_only = @event.Teamonly,
            text = @event.Text ?? ""
        });
        if (play4lanWebChat.Count > 120) play4lanWebChat.RemoveRange(0, play4lanWebChat.Count - 120);
        return HookResult.Continue;
    }

    private List<P4LPlayerState> P4LPlayers()
    {
        var rows = new List<P4LPlayerState>();
        foreach (var kv in playerData)
        {
            int userid = kv.Key;
            var p = kv.Value;
            if (p == null || !p.IsValid || p.IsBot || p.IsHLTV) continue;
            string side = p.TeamNum == 2 ? "TR" : p.TeamNum == 3 ? "CT" : "SPEC";
            bool ready = playerReadyStatus.TryGetValue(userid, out bool rv) && rv;
            int health=0, armor=0, money=0, kills=0, deaths=0, assists=0, damage=0;
            string weapon="";
            try {
                var pawn = p.PlayerPawn.Value;
                if (pawn != null && pawn.IsValid) {
                    health = Math.Max(0, pawn.Health);
                    armor = Math.Max(0, pawn.ArmorValue);
                    var active = pawn.WeaponServices?.ActiveWeapon.Value;
                    if (active != null && active.IsValid) weapon = (active.DesignerName ?? "").Replace("weapon_", "");
                }
                if (p.InGameMoneyServices != null) money = p.InGameMoneyServices.Account;
                if (p.ActionTrackingServices != null) {
                    var stats = p.ActionTrackingServices.MatchStats;
                    kills = stats.Kills; deaths = stats.Deaths; assists = stats.Assists; damage = stats.Damage;
                }
            } catch { }
            rows.Add(new P4LPlayerState {
                userid=userid, steam_id64=p.SteamID, name=p.PlayerName, team=side,
                team_name=(p.TeamNum==2 || p.TeamNum==3) ? Play4LanTeamName(p.TeamNum) : "ESPECTADOR",
                ready=ready, ping=(int)p.Ping, alive=health>0, health=health, armor=armor, money=money,
                kills=kills, deaths=deaths, assists=assists, damage=damage, weapon=weapon
            });
        }
        return rows;
    }

    private List<P4LBackupItem> P4LBackups()
    {
        var rows = new List<P4LBackupItem>();
        try {
            string folder = Path.Combine(Server.GameDirectory, "csgo", "PLAY4LANDataBackup");
            if (!Directory.Exists(folder)) return rows;
            var rx = new Regex(@"_round(?<r>\d+)\.json$", RegexOptions.IgnoreCase);
            foreach (string path in Directory.GetFiles(folder, "play4lan_*_round*.json")) {
                string file = Path.GetFileName(path);
                var m = rx.Match(file);
                int round = m.Success && int.TryParse(m.Groups["r"].Value, out int r) ? r : -1;
                rows.Add(new P4LBackupItem { file=file, round=round, modified_unix=new DateTimeOffset(File.GetLastWriteTimeUtc(path)).ToUnixTimeSeconds() });
            }
        } catch { }
        return rows.OrderByDescending(x => x.modified_unix).Take(40).ToList();
    }

    [ConsoleCommand("css_play4lan_state", "Estado completo do servidor para o painel PLAY4LAN")]
    public void OnPlay4LanWebState(CCSPlayerController? player, CommandInfo command)
    {
        int a=0,b=0; try { (a,b)=GetTeamsScore(); } catch { }
        var state = new P4LServerState {
            map=Server.MapName, phase=P4LPhase(), paused=isPaused, test_mode=play4lanTestMode,
            team1_score=a, team2_score=b, players=P4LPlayers(), chat=play4lanWebChat.ToList(), backups=P4LBackups()
        };
        command.ReplyToCommand("PLAY4LAN_STATE_JSON " + JsonSerializer.Serialize(state));
    }

    [ConsoleCommand("css_play4lan_ready", "Define pronto/espera pelo painel")]
    public void OnPlay4LanWebReady(CCSPlayerController? player, CommandInfo command)
    {
        if (player != null && !IsPlayerAdmin(player, "css_play4lan_ready", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (command.ArgCount < 3 || !int.TryParse(command.ArgByIndex(1), out int userid)) { command.ReplyToCommand("Uso: css_play4lan_ready <userid> <1|0>"); return; }
        if (!playerData.TryGetValue(userid, out var target) || target == null || !target.IsValid) { command.ReplyToCommand("[PLAY4LAN] Jogador não encontrado."); return; }
        if (matchStarted) { command.ReplyToCommand("[PLAY4LAN] Não é possível alterar pronto após o início."); return; }
        bool value = command.ArgByIndex(2) == "1";
        if (value && target.TeamNum != 2 && target.TeamNum != 3) { command.ReplyToCommand("[PLAY4LAN] Jogador precisa estar em TR ou CT."); return; }
        playerReadyStatus[userid]=value;
        if (value) play4lanReadyLockedTeam[userid]=target.TeamNum; else play4lanReadyLockedTeam.Remove(userid);
        PrintToAllChat(value ? $"{ChatColors.Green}✓ {target.PlayerName}{ChatColors.Default} foi marcado PRONTO pelo árbitro." : $"{target.PlayerName} foi colocado EM ESPERA pelo árbitro.");
        command.ReplyToCommand($"[PLAY4LAN] {target.PlayerName}: {(value ? "PRONTO" : "EM ESPERA")}");
        CheckLiveRequired(); HandleClanTags();
    }

    [ConsoleCommand("css_play4lan_admin_pause", "Pausa administrativa")]
    public void OnPlay4LanWebPause(CCSPlayerController? player, CommandInfo command)
    {
        if (player != null && !IsPlayerAdmin(player, "css_play4lan_admin_pause", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (isPaused) { command.ReplyToCommand("[PLAY4LAN] Já está pausada."); return; }
        unpauseData["pauseTeam"]="Admin"; SetMatchPausedFlags(); command.ReplyToCommand("[PLAY4LAN] Partida pausada pelo painel.");
    }

    [ConsoleCommand("css_play4lan_admin_resume", "Retomada única do painel")]
    public void OnPlay4LanWebResume(CCSPlayerController? player, CommandInfo command)
    {
        if (player != null && !IsPlayerAdmin(player, "css_play4lan_admin_resume", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (isPaused) UnpauseMatch(); else Server.ExecuteCommand("mp_unpause_match;");
        command.ReplyToCommand("[PLAY4LAN] Partida retomada pelo painel.");
    }

    [ConsoleCommand("css_play4lan_restore", "Restaura backup PLAY4LAN")]
    public void OnPlay4LanWebRestore(CCSPlayerController? player, CommandInfo command)
    {
        if (player != null && !IsPlayerAdmin(player, "css_play4lan_restore", "@css/config")) { SendPlayerNotAdminMessage(player); return; }
        if (command.ArgCount < 2) { command.ReplyToCommand("Uso: css_play4lan_restore <arquivo.json>"); return; }
        string file=command.ArgByIndex(1).Trim();
        if (Path.GetFileName(file)!=file || !file.StartsWith("play4lan_", StringComparison.OrdinalIgnoreCase) || !file.EndsWith(".json", StringComparison.OrdinalIgnoreCase)) { command.ReplyToCommand("[PLAY4LAN] Backup inválido."); return; }
        RestoreRoundBackup(player, file);
    }
}
