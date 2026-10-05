"""Mapas competitivos: nome exibido no site <-> nome do mapa no servidor."""

MAPS = {
    'Mirage': 'de_mirage', 'Inferno': 'de_inferno', 'Nuke': 'de_nuke', 'Ancient': 'de_ancient',
    'Anubis': 'de_anubis', 'Dust II': 'de_dust2', 'Train': 'de_train', 'Overpass': 'de_overpass',
    'Vertigo': 'de_vertigo', 'Cache': 'de_cache',
}
# Cor de fundo dos cards de veto (sem usar arte oficial dos mapas).
MAP_COLORS = {
    'Mirage': '#c9a15a', 'Inferno': '#c4553b', 'Nuke': '#4f8fb8', 'Ancient': '#4f8a5b', 'Anubis': '#d0a347',
    'Dust II': '#d7b46a', 'Train': '#6f7f8f', 'Overpass': '#5e9b8a', 'Vertigo': '#7c8fb5', 'Cache': '#8f9a5a',
}
ALL_MAPS = list(MAPS)

def server_name(display): return MAPS.get(display, display if display.startswith('de_') else 'de_' + display.lower().replace(' ', ''))

def display_name(server):
    for d, s in MAPS.items():
        if s == server: return d
    return (server or '').replace('de_', '').replace('_', ' ').title()
