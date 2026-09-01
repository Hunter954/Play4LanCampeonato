# Controle interno do CS2 via RCON

Este pacote adiciona ao painel administrativo:

- página interna de cada servidor;
- leitura de `status` via RCON;
- jogadores conectados (quando o formato retornado pelo CS2 for reconhecido);
- kick por `userid`;
- console RCON bruto;
- encerrar warmup;
- reiniciar jogo em 1 segundo;
- pause/unpause de teste;
- troca de mapa;
- histórico de comandos e resultado/erro;
- telemetria enviada pelo Agent a cada heartbeat.

## 1. Atualize o código no Railway e no PC

Suba esta versão no GitHub. Aguarde o redeploy do serviço Web no Railway. No PC da LAN, atualize os arquivos do Agent com a mesma versão.

## 2. Configure `agent/config.json`

Não envie este arquivo para o GitHub. Para o SERVER01, use a mesma senha em dois lugares:

```json
"args": [
  "-dedicated", "-console", "-usercon",
  "-port", "27015",
  "+game_type", "0", "+game_mode", "1",
  "+rcon_password", "SUA_SENHA_RCON",
  "+map", "de_mirage"
],
"rcon_host": "127.0.0.1",
"rcon_port": 27015,
"rcon_password": "SUA_SENHA_RCON"
```

A senha fica somente no PC da LAN. Não coloque senha real em `config.example.json`.

## 3. Reinicie o servidor pelo painel

A senha passada por `+rcon_password` só é aplicada quando o processo do CS2 inicia. Portanto, depois de alterar o config, pare o servidor e inicie novamente pelo Agent/painel.

## 4. Abra o console do servidor

No painel administrativo:

`Admin > Servidores > Abrir console`

O Agent consulta `status` a cada heartbeat. O painel mostra mapa, quantidade de jogadores e RCON.

## 5. Teste

No campo Console RCON, envie:

```text
status
```

Depois teste:

```text
mp_warmup_end
```

ou use os botões do painel.

## Observação

Esta etapa é o controle básico do servidor. Faca, `.ficar/.trocar`, `.pause/.tac 3/3`, `.tec`, stats avançadas e restore serão implementados na camada competitiva seguinte.
