# Deploy no Railway

## 1. GitHub
Suba o CONTEÚDO da pasta `cs2-platform` para um repositório GitHub. Não envie o ZIP como arquivo único.

## 2. Railway
Crie um projeto e adicione:

1. Um serviço **PostgreSQL**.
2. Um serviço **Web** conectado ao repositório GitHub.

O projeto usa Railpack automaticamente por causa do `requirements.txt` e `.python-version`.

## 3. Start Command
O `Procfile` já contém:

```bash
gunicorn -k gevent -w 1 --bind 0.0.0.0:$PORT web.run:app
```

Se o Railway pedir Start Command manualmente, use exatamente o comando acima.

## 4. Variáveis no serviço Web
Use estas variáveis:

```env
FLASK_ENV=production
SECRET_KEY=COLOQUE_UMA_CHAVE_GRANDE_ALEATORIA
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_EMAIL=seu-email
ADMIN_PASSWORD=uma-senha-forte
STEAM_API_KEY=sua-chave-steam
AGENT_SHARED_TOKEN=UM_TOKEN_GRANDE_ALEATORIO
MAX_CONTENT_LENGTH_MB=1024
```

Depois de gerar o domínio público do serviço Web, adicione também:

```env
PUBLIC_BASE_URL=https://SEU-DOMINIO.up.railway.app
STEAM_REALM=https://SEU-DOMINIO.up.railway.app
```

Se o serviço PostgreSQL tiver outro nome no Railway, substitua `Postgres` na referência `DATABASE_URL=${{Postgres.DATABASE_URL}}` pelo nome real do serviço.

## 5. Storage de demos
Pode ser configurado depois. Sem S3/Bucket, as funções que dependem de storage online não devem ser consideradas persistentes.

Variáveis previstas:

```env
S3_ENDPOINT_URL=
S3_REGION=
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_BUCKET=
```

## 6. Agent local
A pasta `agent/` fica no mesmo GitHub, mas NÃO é um segundo serviço Railway. Ela é executada no PC do campeonato.

No PC:

```bash
pip install -r requirements.txt
copy agent\config.example.json agent\config.json
python -m agent.main
```

No `agent/config.json`, a URL deve ser o domínio online da plataforma e o token precisa ser exatamente o mesmo `AGENT_SHARED_TOKEN` configurado no Railway.
