# WebSocket Proxy Fix (Werkzeug 3.1+)

## O Problema

Durante a atualização do EvoNexus para a versão `v0.33.0` (ou qualquer ambiente usando Flask 3.0+ e Werkzeug 3.1+), os terminais começaram a sofrer fechamentos repentinos com o erro "WebSocket error" no frontend.

A investigação revelou que o problema ocorria devido a uma mudança arquitetural no **Werkzeug**. A partir da versão 2.1, o Werkzeug removeu o suporte nativo a *WebSocket Hijacking* no seu servidor WSGI de desenvolvimento.

A extensão `flask-sock` e o pacote subjacente `simple-websocket` utilizam *monkey-patching* para restaurar esse suporte, exigindo que as regras de rota WebSocket tenham o sinalizador `websocket=True` habilitado internamente. 
No entanto, quando a aplicação roda atrás de um proxy reverso (como o **Traefik** no ambiente de produção da VPS), os cabeçalhos de *Upgrade* são repassados como `HTTP_UPGRADE: websocket`. Como o ambiente WSGI gerado não contém a variável interna `wsgi.websocket = True`, o sistema de roteamento do Werkzeug considera que a requisição **não é** um WebSocket.

**A Cascata de Falhas:**
1. O navegador conecta-se a `wss://<dominio>/terminal/ws`.
2. O Traefik encaminha para o Flask com `HTTP_UPGRADE: websocket`.
3. O Werkzeug avalia a rota `/terminal/ws` do `flask-sock` (que exige `wsgi.websocket = True`), avalia como **falsa** (não correspondente) e **pula** essa rota.
4. A requisição "cai" na rota coringa de proxy HTTP (`/terminal/<path:subpath>`).
5. A rota HTTP converte a requisição WebSocket num `GET` normal e envia para o servidor Node.js interno do terminal (`:32352/ws`).
6. O servidor Node.js não encontra uma página HTTP em `/ws` e retorna **404 Not Found**.
7. O Flask retorna o `404` embutido num status `200 OK`, destruindo a negociação do WebSocket e derrubando a conexão.

## A Solução

Foi implementado um **WSGI Middleware** (`ProxyFixWSGI`) no arquivo `dashboard/backend/app.py`.

```python
class ProxyFixWSGI:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # Fix for modern Werkzeug (3.0+) not matching websocket=True rules
        # when running behind proxies that don't set wsgi.websocket.
        if environ.get("HTTP_UPGRADE", "").lower() == "websocket":
            environ["wsgi.websocket"] = True
        return self.wsgi_app(environ, start_response)
```

**Como funciona?**
Este middleware intercepta as requisições *antes* delas entrarem na esteira de roteamento do Flask/Werkzeug. Ele examina os cabeçalhos em busca de uma solicitação de `Upgrade: websocket`. Caso encontre, ele injeta artificialmente a chave `environ["wsgi.websocket"] = True` no ambiente WSGI.

Ao fazer isso, quando a requisição atinge o sistema de roteamento (o `MapAdapter`), o Werkzeug avalia a rota do `flask-sock` como perfeitamente válida para WebSockets, permitindo que o tráfego seja roteado corretamente para a função `proxy_ws` em `terminal_proxy.py`, mantendo a persistência, resiliência e validação correta do túnel WebSocket no terminal do usuário.

Adicionalmente, no arquivo `terminal_proxy.py`, a rota foi estabilizada e configurada com prioridade de escopo para sempre anteceder a rota de coringa HTTP, blindando o sistema contra eventuais falhas do sistema de peso do URL Map do Flask.
