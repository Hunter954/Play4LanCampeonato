# CS2 Championship Platform MVP

Plataforma híbrida para campeonato presencial de CS2.

- **web/**: Flask + PostgreSQL + portal público + admin + Steam OpenID + times + convites + inscrições + demos + API do host.
- **agent/**: Python rodando no PC do campeonato; heartbeat, fila SQLite offline, start/stop dos servidores e upload de demos.

## Arquitetura

**Online / Railway:** Flask + PostgreSQL + storage S3 compatível.

**PC local:** Python Agent + Server 01 + Server 02 + SQLite de emergência.

## Primeiro uso local

1. Copie `.env.example` para `.env`.
2. Crie um PostgreSQL e ajuste `DATABASE_URL`, ou use SQLite apenas para desenvolvimento local.
3. Instale: `pip install -r requirements.txt`.
4. Rode: `python -m web.run`.
5. Abra `http://127.0.0.1:5000`.

## Admin inicial

Defina `ADMIN_EMAIL` e `ADMIN_PASSWORD` no `.env`. Ao iniciar, a conta é criada automaticamente.

## Railway

Veja `RAILWAY_SETUP.md`.

O serviço online usa:

```bash
gunicorn -k gevent -w 1 --bind 0.0.0.0:$PORT web.run:app
```

## Agent local

No PC do campeonato:

```bash
python -m agent.main
```

Configure `agent/config.json` a partir de `agent/config.example.json`.

## Limite atual

Este ZIP entrega a fundação e fluxos web principais. Regras que precisam executar dentro do CS2 — por exemplo interceptar `.tac`, knife round e eventos completos por jogador — dependem de integração específica via plugin existente, RCON e/ou logs. O projeto evita plugin próprio em C# e deixa os adaptadores preparados em `agent/cs2.py`.
