from pathlib import Path

root = Path('upstream')


def replace_method(path: Path, signature: str, replacement: str):
    s = path.read_text(encoding='utf-8')
    start = s.index(signature)
    brace = s.index('{', start)
    depth = 0
    end = None
    for i in range(brace, len(s)):
        if s[i] == '{': depth += 1
        elif s[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    s = s[:start] + replacement + s[end:]
    path.write_text(s, encoding='utf-8')

p = root / 'MatchZy.cs'
s = p.read_text(encoding='utf-8').replace('public override string ModuleVersion => "1.0.5";', 'public override string ModuleVersion => "1.0.6";')
p.write_text(s, encoding='utf-8')

p = root / 'Utility.cs'
replace_method(p, 'private void CheckLiveRequired()', r'''private void CheckLiveRequired()
        {
            if (!readyAvailable || matchStarted) return;
            if (play4lanTestMode)
            {
                int ready = playerReadyStatus.Count(kv => kv.Value == true);
                if (ready >= 1)
                {
                    PrintToAllChat($"{ChatColors.Green}MODO TESTE PLAY4LAN: 1 jogador pronto. Iniciando ROUND FACA...{ChatColors.Default}");
                    isKnifeRequired = true;
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
            else if (!allReady) play4lanAllReadyAnnounced = false;
        }''')

source = Path('PLAY4LANCompetitive/Play4LanWebOps.cs')
(root / 'Play4LanWebOps.cs').write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
print('PLAY4LAN v1.0.6 aplicado.')
