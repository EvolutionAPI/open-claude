# SPEC: EvoNexus & Agro Roraima Contábil

## Visão Geral
Sistema Multiagentes Autônomos (SMA) local-first baseado no framework OpenClaw, voltado para automação de processos contábeis, tributários e burocráticos do Agronegócio (Agro Roraima Contábil). O painel administrativo (Dashboard) integra gestão de usuários, observabilidade de integrações (WhatsApp, Telegram) e controle total do pipeline de agentes.

## Sprint Atual: Configuração e Escala
**Entregável:** Sistema estável com normalização de variáveis de ambiente, roteamento de provedores (OpenRouter) e painéis de observabilidade operacionais.
**Risco:** Alto (Lida com dados sensíveis de folha de pagamento e impostos federais).

---

### Feature 1: Roteamento de Provedores de IA (Smart Router)
**Categoria:** ia_agent
**Descrição:** O sistema deve suportar falha e troca dinâmica de provedores (ex: OpenRouter para Anthropic), derrubando sessões antigas para evitar loops e travamentos.

**Steps:**
1. Painel frontend permite alteração do provedor principal.
2. Backend (Flask) notifica o Terminal Server via rota HTTP.
3. Terminal Server invalida sessões PTY ativas (`ClaudeBridge.invalidateAllSessions()`).
4. Agentes reconectam usando as novas chaves.

**Edge cases (Tratamento Automático):**
- E se o novo provedor estiver fora do ar: Fallback configurado no `provider-config.js`.
- Limite de tokens (Rate Limit do provedor): Backoff exponencial e retry.
- Modelo indisponível: Reverter para o modelo secundário definido na configuração.

---

### Feature 2: Proteção Contra Força Bruta (Auth Hardening)
**Categoria:** auth
**Descrição:** Limitar tentativas de login falhas por usuário/IP para proteger contra ataques de força bruta.

**Steps:**
1. Usuário tenta login com credenciais inválidas.
2. Registro de `login_throttles` é incrementado no banco de dados.
3. Se tentativas falhas == 5, aplicar bloqueio de 5 minutos.
4. Se tentativas falhas >= 10, aplicar bloqueio de 30 minutos.

**Edge cases (Tratamento Automático):**
- Sessão expirada no meio da navegação: Redirecionar para login sem crashar o app.
- Proteção CSRF ausente: Rejeitar a mutação com status 403.

---

### Feature 3: Automação EFD-Contribuições (Integração SPED)
**Categoria:** api_endpoint
**Descrição:** Agente Fiscal deve extrair dados estruturados (notas fiscais) e gerar arquivo no formato SPED delimitado por *pipe* (|).

**Steps:**
1. Agente aciona ferramenta (skill) `sped_cli.py`.
2. Leitura massiva de diretório de faturas via OCR/JSON.
3. Validação dos blocos (0000, 0001, 0100).
4. Emissão de relatório de aprovação.

**Edge cases:**
- Falha na leitura do OCR (fatura borrada): Alertar o Humano (Human-in-the-loop) para input manual.
- E se a alíquota for alterada por nova lei: Bloquear emissão até que a tabela seja atualizada.
