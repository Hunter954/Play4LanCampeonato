from pathlib import Path

# Namespace atual do atributo ConsoleCommand.
p = Path('upstream/Play4LanCommands.cs')
s = p.read_text(encoding='utf-8')
needle = 'using CounterStrikeSharp.API.Core;\n'
insert = 'using CounterStrikeSharp.API.Core;\nusing CounterStrikeSharp.API.Core.Attributes.Registration;\n'
if 'CounterStrikeSharp.API.Core.Attributes.Registration' not in s:
    s = s.replace(needle, insert)
p.write_text(s, encoding='utf-8')

# Compatibilidade com CounterStrikeSharp 1.0.373: o enum passou de
# PlayerConnectedState.PlayerConnected para PlayerConnectedState.Connected.
for p in Path('upstream').glob('*.cs'):
    s = p.read_text(encoding='utf-8')
    ns = s.replace('PlayerConnectedState.PlayerConnected', 'PlayerConnectedState.Connected')
    if ns != s:
        p.write_text(ns, encoding='utf-8')

print('Compatibilidade CounterStrikeSharp 1.0.373 aplicada.')