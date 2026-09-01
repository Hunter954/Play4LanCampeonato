from pathlib import Path
p = Path('upstream/Play4LanCommands.cs')
s = p.read_text(encoding='utf-8')
needle = 'using CounterStrikeSharp.API.Core;\n'
insert = 'using CounterStrikeSharp.API.Core;\nusing CounterStrikeSharp.API.Core.Attributes.Registration;\n'
if 'CounterStrikeSharp.API.Core.Attributes.Registration' not in s:
    s = s.replace(needle, insert)
p.write_text(s, encoding='utf-8')
print('Namespace de ConsoleCommand adicionado.')