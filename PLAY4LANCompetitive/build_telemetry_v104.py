from pathlib import Path

root = Path('upstream')

# Bump da versao.
p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8')
s = s.replace('public override string ModuleVersion => "1.0.3";', 'public override string ModuleVersion => "1.0.4";')
p.write_text(s, encoding='utf-8')

# Canal estruturado de jogadores para o Agent PLAY4LAN.
(root / 'Play4LanTelemetry.cs').write_text(r'''using System.Collections.Generic;
using System.Text.Json;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Core.Attributes.Registration;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Utils;

namespace MatchZy;

public partial class MatchZy
{
    private sealed class Play4LanPlayerTelemetry
    {
        public int userid { get; set; }
        public ulong steam_id64 { get; set; }
        public string name { get; set; } = "";
        public int team_num { get; set; }
        public string team { get; set; } = "SPEC";
        public string team_name { get; set; } = "ESPECTADOR";
        public bool ready { get; set; }
    }

    [ConsoleCommand("css_play4lan_players", "Retorna jogadores conectados em JSON para o Agent PLAY4LAN")]
    [ConsoleCommand("css_p4l_players", "Retorna jogadores conectados em JSON para o Agent PLAY4LAN")]
    public void OnPlay4LanPlayersTelemetry(CCSPlayerController? player, CommandInfo command)
    {
        var rows = new List<Play4LanPlayerTelemetry>();

        foreach (var item in playerData)
        {
            int userid = item.Key;
            CCSPlayerController p = item.Value;
            if (p == null || !p.IsValid || p.IsBot || p.IsHLTV) continue;

            bool isReady = playerReadyStatus.TryGetValue(userid, out bool readyValue) && readyValue;
            string side = p.TeamNum == (int)CsTeam.Terrorist ? "TR" :
                          p.TeamNum == (int)CsTeam.CounterTerrorist ? "CT" : "SPEC";
            string teamName = p.TeamNum == (int)CsTeam.Terrorist || p.TeamNum == (int)CsTeam.CounterTerrorist
                ? Play4LanTeamName(p.TeamNum)
                : "ESPECTADOR";

            rows.Add(new Play4LanPlayerTelemetry
            {
                userid = userid,
                steam_id64 = p.SteamID,
                name = p.PlayerName,
                team_num = p.TeamNum,
                team = side,
                team_name = teamName,
                ready = isReady
            });
        }

        command.ReplyToCommand("PLAY4LAN_PLAYERS_JSON " + JsonSerializer.Serialize(rows));
    }
}
''', encoding='utf-8')

print('PLAY4LAN v1.0.4 aplicado: telemetria estruturada de jogadores via css_play4lan_players.')
