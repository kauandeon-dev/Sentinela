# Sentinela — Backup Automatizado

**Sistema open source de backup automatizado para pequenas empresas que usam bancos de dados
relacionais — PostgreSQL e MariaDB/MySQL — locais ou em outro servidor, via túnel SSH.**

Projeto Integrador · Curso Técnico · IFSC Câmpus São Lourenço do Oeste · 2026
Autor: **Kauan V. Machado Deon** · Licença MIT

![Painel do Sentinela](docs/img/painel.png)

---

## Sumário

1. [Por que o Sentinela existe](#1-por-que-o-sentinela-existe)
2. [O que ele faz](#2-o-que-ele-faz)
3. [Telas](#3-telas)
4. [Como funciona por dentro](#4-como-funciona-por-dentro)
5. [Instalação](#5-instalação)
6. [Guia de uso — tela por tela](#6-guia-de-uso--tela-por-tela)
7. [Preparando o banco de dados](#7-preparando-o-banco-de-dados)
8. [Banco em outro servidor: túnel SSH](#8-banco-em-outro-servidor-túnel-ssh)
9. [Linha de comando](#9-linha-de-comando)
10. [Configuração (variáveis de ambiente)](#10-configuração-variáveis-de-ambiente)
11. [Recuperação de desastre](#11-recuperação-de-desastre)
12. [Segurança](#12-segurança)
13. [Solução de problemas](#13-solução-de-problemas)
14. [Testes](#14-testes)
15. [Estrutura do código e API](#15-estrutura-do-código-e-api)
16. [Limitações conhecidas](#16-limitações-conhecidas)

---

## 1. Por que o Sentinela existe

Muitas pequenas empresas já usam sistemas informatizados, mas não têm um backup **automático,
seguro e conferido**. O problema é sério: 60% das pequenas empresas encerram as atividades em até
seis meses após uma perda grave de dados, 51% dos ataques de *ransomware* tentam destruir os
backups da vítima e cerca de 58% dos backups corporativos falham — muitas vezes sem que ninguém
perceba até a hora de restaurar (ver referências no documento do projeto).

A motivação prática veio da migração de dados entre ERPs de provedores de internet: o backup
fornecido por alguns sistemas é **incompleto** (dados visíveis na interface não aparecem no dump)
ou depende do fornecedor. O Sentinela devolve o controle ao dono dos dados: faz a cópia do banco
inteiro, protege, confere e avisa quando algo dá errado — em vez de falhar em silêncio.

## 2. O que ele faz

| Requisito do projeto | Como o Sentinela atende |
|---|---|
| Interface para configurar a política de backup | Painel web com login: Painel, Política, Histórico, Logs e Conexão |
| Agendamento automático | Diário à meia-noite **ou** a cada *N* dias (1–30), sem intervenção manual |
| Retenção configurável (máx. 10 dias) | Exclusão automática das cópias expiradas (1–10 dias). A cópia válida mais recente nunca é apagada |
| Extração via dump — PostgreSQL e MariaDB | `pg_dump` ou `mariadb-dump`/`mysqldump`, escolhido na tela Conexão |
| Banco em outro servidor | Conexão direta **ou túnel SSH** (senha ou chave privada), com verificação da chave do servidor |
| Criptografia | **AES-256-GCM** — confidencialidade **e** detecção de adulteração |
| Compressão | **gzip**, aplicada em fluxo antes da criptografia (≈ −90% em bases típicas) |
| Armazenamento isolado (regra 3-2-1) | Diretório dedicado, validado fora da aplicação; pode ser disco externo, NFS, SMB… |
| Log detalhado a cada execução | Cada etapa com horário exato, no **terminal ao vivo** do painel e em arquivos `.log` |
| Verificação de integridade | Após **cada** backup e sob demanda: SHA-256, autenticação GCM, gzip, fim do dump e contagem de rotinas |
| Teste de restauração | Restauração pelo painel, com verificação prévia e **cópia automática do estado atual** antes de sobrescrever |

Além do escopo original:

- **Terminal de logs ao vivo** (estilo `tail -f`) com filtros, busca e progresso do dump em MB/s.
- **Painel de execução em andamento** com etapas, progresso e últimas linhas do log.
- **Checklist "Saúde da proteção"** e gráfico das últimas cópias.
- **Detecção de backup incompleto**: o `mariadb-dump` pula em silêncio rotinas que o usuário não
  enxerga; o Sentinela confere e acusa.
- **Tema escuro**, layout responsivo (funciona no celular) e linha de comando para cron e recuperação.

## 3. Telas

| | |
|---|---|
| ![Backup em andamento](docs/img/painel-ao-vivo.png) **Backup em andamento** — etapas, progresso e log ao vivo | ![Terminal de logs](docs/img/logs-ao-vivo.png) **Terminal de logs** — linhas chegando em tempo real |
| ![Conexão via SSH](docs/img/conexao-ssh.png) **Conexão** — direta ou via túnel SSH | ![Detalhe da cópia](docs/img/detalhe.png) **Detalhe** — metadados, integridade, restaurar, baixar |
| ![Histórico](docs/img/historico.png) **Histórico** — filtros por tipo e falhas | ![Política](docs/img/politica.png) **Política** — agendamento, retenção, segurança |
| ![Tema escuro](docs/img/painel-escuro.png) **Tema escuro** | ![Logs no tema escuro](docs/img/logs-escuro.png) **Logs no tema escuro** |

<p align="center"><img src="docs/img/celular.png" width="300" alt="Sentinela no celular"></p>

---

## 4. Como funciona por dentro

### 4.1 Arquitetura

```mermaid
flowchart LR
    U([Administrador<br>navegador]) -- HTTPS/HTTP --> W[web.py<br>API JSON + painel]
    W --> E[engine.py<br>backup · verificação<br>restauração · retenção]
    S[scheduler.py<br>agendador] --> E
    E --> D[dumpers.py<br>pg_dump / mariadb-dump]
    D -- direto --> DB[(Banco de dados)]
    D -- ou --> T[tunnel.py<br>túnel SSH] --> SSH[Servidor SSH] --> DB
    E --> C[crypto.py<br>gzip + AES-256-GCM]
    C --> B[/Diretório de backup<br>isolado/]
    E --> ST[(storage.py<br>SQLite: configurações,<br>histórico e logs)]
    E --> L[/arquivos de log/]
```

Tudo roda em **um único processo** Python: o servidor web (waitress) e, em paralelo, a thread do
agendador. Não há serviço externo além do banco que será copiado.

### 4.2 Ciclo de um backup

```mermaid
sequenceDiagram
    autonumber
    participant A as Agendador / botão
    participant E as Sentinela
    participant T as Túnel SSH (opcional)
    participant DB as Banco
    participant F as Diretório de backup
    A->>E: iniciar backup
    E->>T: abrir túnel e conferir chave do servidor
    E->>DB: testar conexão (SELECT version())
    E->>DB: pré-verificação (ex.: rotinas do MariaDB)
    DB-->>E: dump em fluxo (pg_dump / mariadb-dump)
    E->>F: gzip → AES-256-GCM → arquivo .part
    E->>F: rename atômico → .sql.gz.enc
    E->>F: reler tudo: SHA-256, tag GCM, gzip, fim do dump
    E->>E: registrar no histórico e aplicar retenção
    E->>T: fechar túnel
```

Cada etapa vira uma linha de log com horário. Um backup real, via SSH:

```
15:57:10  INFO  Iniciando backup manual · PostgreSQL
15:57:10  INFO  Abrindo túnel SSH para tunel@10.77.0.2:22
15:57:11  OK    Túnel SSH estabelecido · chave do host SHA256:RLxWIT5X…
15:57:11  INFO  Conectando ao banco "loja_remota" em localhost:5432 via SSH 10.77.0.2
15:57:11  OK    Conexão estabelecida · PostgreSQL 16.13
15:57:11  INFO  Gerando dump em fluxo: dump → gzip → AES-256-GCM
15:57:13  INFO  Dump em andamento: 108,0 MB · 54,0 MB/s
15:57:14  OK    Dump gerado com sucesso (136,1 MB)
15:57:14  OK    Arquivo comprimido com gzip (10,4 MB · −92,4%)
15:57:14  OK    Arquivo criptografado com AES-256-GCM
15:57:14  OK    Cópia armazenada em /backups/loja_remota_20260929_155710.sql.gz.enc
15:57:14  INFO  SHA-256 eda788e8bc617987828a7a6c746d030c6bbbb2ed7489aea14944c74a10bbee8d
15:57:14  OK    Integridade verificada: arquivo legível e dump completo
15:57:14  OK    Backup concluído em 4s
```

Pontos importantes do desenho:

- **Em fluxo (streaming):** o SQL em texto claro **nunca** é gravado em disco e bancos grandes não
  são carregados na memória. A saída do `pg_dump` passa por gzip e AES em blocos de 1 MB.
- **Gravação atômica:** o arquivo é escrito como `.part` e só depois renomeado. Um dump interrompido
  (queda de rede, banco reiniciado, disco cheio) **nunca** vira uma cópia "válida".
- **Conferência do fim do dump:** o `pg_dump` termina com `PostgreSQL database dump complete` e o
  `mariadb-dump` com `Dump completed`. Sem esse marcador, a cópia é rejeitada.

### 4.3 Formato do arquivo de backup

Nome: `<banco>_<AAAAMMDD>_<HHMMSS>.sql[.gz][.enc]` — as extensões indicam as camadas aplicadas.

Arquivo criptografado (`.enc`):

```
┌──────────┬────────┬──────────────┬─────────────────────────────┬──────────────┐
│ "SNTL"   │ versão │ nonce (12 B) │ SQL comprimido e cifrado    │ tag GCM (16) │
│ 4 bytes  │ 1 byte │ aleatório    │ AES-256-GCM                 │ autenticação │
└──────────┴────────┴──────────────┴─────────────────────────────┴──────────────┘
```

O cabeçalho entra como dado autenticado (AAD): alterar **qualquer** byte do arquivo — cabeçalho ou
conteúdo — faz a verificação falhar. Além disso, o SHA-256 do arquivo é registrado no histórico.

### 4.4 Verificação de integridade

Feita automaticamente logo após cada backup e, sob demanda, pelo botão **Verificar integridade**:

1. o arquivo existe no diretório;
2. o **SHA-256** confere com o registrado no momento da criação;
3. a **tag AES-256-GCM** é válida (arquivo íntegro e chave correta);
4. o **gzip** descomprime até o fim;
5. o SQL termina com o **marcador de dump completo**.

No MariaDB há ainda a **conferência de completude**: antes do dump o Sentinela conta as
procedures/functions do banco direto em `mysql.proc`; depois conta as que entraram na cópia.
Faltou alguma → o backup **falha** com a explicação. Se o usuário não tem permissão para fazer essa
contagem, o log e o checklist mostram um aviso com o `GRANT` necessário (ver [seção 7](#7-preparando-o-banco-de-dados)).

### 4.5 Restauração

```mermaid
flowchart LR
    A[Confirmar no painel] --> B[Verificar a cópia<br>SHA-256 · GCM · gzip · fim]
    B --> C[Backup automático<br>do estado atual<br>'pré-restauração']
    C --> D[Aplicar o dump<br>psql / mariadb]
    D --> E[Log + histórico]
```

- **PostgreSQL:** o dump é aplicado com `--single-transaction` e `ON_ERROR_STOP` — ou tudo é
  restaurado, ou nada muda.
- **MariaDB:** o cliente não restaura de forma atômica. Se algo falhar no meio, a mensagem de erro
  indica a **cópia pré-restauração** que devolve o banco ao estado anterior.
- **Objetos com dono (DEFINER) no MariaDB:** views, triggers e procedures guardam o usuário que as
  criou (ex.: `root`). Recriá-las com outro dono exigiria privilégio `SUPER`; por isso o Sentinela
  remove a cláusula `DEFINER` durante a restauração (só nos comandos de criação, nunca nos dados) e
  os objetos passam a pertencer ao usuário que restaura.

### 4.6 Agendamento e retenção

- **Diário:** todo dia à meia-noite (horário do servidor). **Intervalo:** a cada *N* dias, à meia-noite.
- Se o servidor estava desligado no horário, o backup roda assim que o Sentinela volta e o próximo
  é reagendado normalmente.
- **Uma execução por vez:** backups, restaurações e verificações nunca rodam em paralelo — nem entre
  o painel e um `sentinela backup` disparado pelo cron (trava de arquivo entre processos).
- **Retenção:** cópias mais antigas que *N* dias (1 a 10) são apagadas após cada backup e a cada hora.
  A **cópia válida mais recente nunca é apagada**, mesmo expirada, para o sistema nunca ficar sem
  nenhum backup restaurável.

### 4.7 Logs

| Onde | O quê |
|---|---|
| Tela **Logs** | Terminal ao vivo com todas as execuções, filtros e busca |
| Tela **Detalhe** | Log da execução daquela cópia (ao vivo enquanto roda) |
| `$SENTINELA_HOME/logs/sentinela.log` | Log geral (rotativo, 5 × 5 MB), inclusive logins e alterações |
| `$SENTINELA_HOME/logs/execucoes/*.log` | Um arquivo por execução (guardados por 90 dias) |

Níveis: `INFO` (etapa iniciada), `OK` (etapa concluída), `WARN` (atenção, mas seguiu) e `ERRO`.

---

## 5. Instalação

### 5.1 Requisitos

- **Linux** (testado em Ubuntu 24.04). Em macOS os requisitos são os mesmos via Homebrew, mas não foi
  testado. No Windows, use o WSL.
- **Python 3.10+**
- **Clientes do banco** instalados na máquina do Sentinela:

| SGBD | Pacote (Debian/Ubuntu) | Comandos usados |
|---|---|---|
| PostgreSQL | `postgresql-client` | `pg_dump`, `psql` |
| MariaDB/MySQL | `mariadb-client` | `mariadb-dump`, `mariadb` (ou `mysqldump`, `mysql`) |

> A versão do `pg_dump` deve ser **igual ou mais nova** que a do servidor PostgreSQL. Use o
> repositório oficial (apt.postgresql.org) se a versão da distribuição for antiga.

### 5.2 Passo a passo

```bash
# 1. dependências do sistema
sudo apt install python3 python3-venv postgresql-client mariadb-client

# 2. código e ambiente Python
sudo git clone https://github.com/kauandeon-dev/Sentinela.git /opt/sentinela
cd /opt/sentinela
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

# 3. usuário do sistema e pastas (dados da aplicação separados das cópias)
sudo useradd --system --home /var/lib/sentinela --shell /usr/sbin/nologin sentinela
sudo install -d -o sentinela -g sentinela -m 700 /var/lib/sentinela /var/backups/sentinela

# 4. primeiro início (mostra a senha inicial do usuário admin)
sudo -u sentinela SENTINELA_HOME=/var/lib/sentinela SENTINELA_BACKUP_DIR=/var/backups/sentinela \
     .venv/bin/python -m sentinela serve
```

Saída do primeiro início:

```
============================================================
 Primeiro acesso: usuário 'admin'  senha: 0EJ0QRHiF_L9VSgi
 Altere com: python -m sentinela passwd admin
============================================================
 Chave mestra: /var/lib/sentinela/sentinela.key
  -> guarde uma cópia FORA do servidor; sem ela as cópias
     criptografadas não podem ser recuperadas.
```

Acesse `http://127.0.0.1:8080` e siga o [guia de uso](#6-guia-de-uso--tela-por-tela).

### 5.3 Como serviço (systemd)

```bash
sudo cp deploy/sentinela.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sentinela
journalctl -u sentinela -f          # acompanhar
```

O arquivo [`deploy/sentinela.service`](deploy/sentinela.service) já vem com as pastas acima e
endurecimento (`ProtectSystem=strict`, `NoNewPrivileges`, `UMask=0077`). Se o diretório de backup
for outro (ex.: um disco externo), inclua-o em `ReadWritePaths`.

### 5.4 Acesso pela rede (HTTPS)

O painel escuta só em `127.0.0.1`. Para acessar de outra máquina, publique atrás de um proxy com
HTTPS e defina `SENTINELA_HTTPS=1`: o cookie de sessão passa a ser só HTTPS e o Sentinela confia no
cabeçalho `X-Forwarded-For` do proxy (para o bloqueio de login valer por IP real). Exemplo com nginx:

```nginx
server {
    listen 443 ssl;
    server_name backup.suaempresa.com.br;
    ssl_certificate     /etc/letsencrypt/live/backup.suaempresa.com.br/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backup.suaempresa.com.br/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. Guia de uso — tela por tela

### 6.1 Entrar

<img src="docs/img/login.png" alt="Tela de login" width="720">

Use o usuário `admin` e a senha mostrada no primeiro início. Para trocar a senha (ou criar outro
usuário): `python -m sentinela passwd admin`. Após 5 tentativas erradas o login é bloqueado por 60 s.

### 6.2 Conexão — configure primeiro

1. **Gerenciador (SGBD):** PostgreSQL ou MariaDB (MySQL). A porta padrão muda sozinha (5432/3306).
2. **Forma de acesso:**
   - **Conexão direta** — o Sentinela alcança a porta do banco pela rede.
   - **Túnel SSH** — o banco está em outro servidor e só o SSH é acessível. Veja a [seção 8](#8-banco-em-outro-servidor-túnel-ssh).
3. **Banco de dados:** host, porta, nome do banco, usuário e senha. Com túnel SSH, o host é o
   endereço do banco **visto pelo servidor SSH** (quase sempre `localhost`).
4. **Testar conexão:** mostra a versão do banco ou o motivo exato da falha.
5. **Diretório de backup:** pasta onde as cópias ficam (fora da pasta da aplicação).
6. **Salvar configurações.** Senhas e chaves já salvas aparecem como "•••••••• (mantida)"; deixe o
   campo vazio para mantê-las.

### 6.3 Política de backup

- **Agendamento:** *Diário à meia-noite* ou *Intervalo personalizado* (a cada 1–30 dias).
- **Retenção:** 1 a 10 dias.
- **Diretório de armazenamento:** o mesmo da tela Conexão. Para a regra 3-2-1, aponte para um disco
  externo, NFS ou pasta sincronizada com outro local.
- **Criptografia (AES-256)** e **Compressão (gzip)**: ligadas por padrão. Desligar a criptografia
  deixa as cópias legíveis por qualquer um com acesso à pasta — o checklist passa a acusar isso.

### 6.4 Painel

- **Indicadores:** status do agendamento, próximo backup, último backup e retenção.
- **Execução em andamento:** aparece durante qualquer backup, verificação ou restauração, com as
  etapas (Conexão → Dump · gzip · AES → Verificação → Concluído), o volume processado, o tempo
  decorrido e as últimas linhas do log.
- **Alerta amarelo:** existe backup com falha entre as cópias guardadas; *Ver logs* abre o detalhe.
- **Últimas execuções:** gráfico com o tamanho de cada cópia; barras vermelhas são falhas. Clique
  numa barra para abrir a cópia.
- **Saúde da proteção:** checklist com a situação atual (cópia recente, integridade, criptografia,
  compressão, túnel SSH, espaço em disco, permissões do usuário de backup e lembrete da chave mestra).
- **Fazer backup agora:** backup manual imediato.

### 6.5 Histórico e detalhe da cópia

O **Histórico** lista as cópias guardadas, com abas *Todos*, *Automáticos*, *Manuais* e *Falhas*.
Clique numa linha para abrir o **detalhe**:

- **Metadados:** tipo, SGBD, banco, tamanho (e tamanho do SQL original), duração, proteção,
  integridade, SHA-256 (com botão copiar) e caminho do arquivo.
- **Restaurar este backup:** substitui o banco atual pela cópia (com confirmação). Antes, o Sentinela
  verifica a cópia e faz um backup do estado atual. Você é levado ao terminal para acompanhar.
- **Verificar integridade:** relê a cópia por completo (seção 4.4).
- **Baixar cópia:** baixa o arquivo como está (criptografado). Para lê-lo fora do painel, use
  `python -m sentinela decrypt`.
- **Excluir cópia:** apaga o arquivo do diretório.
- **Log desta execução:** todas as linhas daquele backup.

### 6.6 Logs — o terminal

- As linhas chegam **ao vivo** (selo "ao vivo" e cursor piscando enquanto algo executa).
- **Seguir novas linhas:** mantém o terminal no fim. Se você rolar para cima para ler algo, ele pausa
  sozinho; volte ao fim para retomar.
- **Filtros:** por nível (INFO, OK, WARN, ERRO) e por tipo (backups, restaurações, verificações).
- **Busca:** destaca o termo em todas as linhas. Atalho: tecla **/**.
- Clique no cabeçalho de uma execução para **recolher/expandir**; o link leva à cópia.
- **Copiar:** copia o que está visível (respeitando filtros). **Baixar logs:** baixa o `sentinela.log`.

### 6.7 Tema escuro

Ícone de lua/sol na barra lateral (e no login). Na primeira visita o painel segue o tema do sistema
operacional; depois, lembra a escolha no navegador.

---

## 7. Preparando o banco de dados

Crie um usuário próprio para o backup. Permissões **testadas** com o Sentinela:

### PostgreSQL

```sql
-- somente backup (leitura de tudo) — PostgreSQL 14+
CREATE ROLE backup_user LOGIN PASSWORD 'troque-esta-senha';
GRANT CONNECT ON DATABASE loja TO backup_user;
GRANT pg_read_all_data TO backup_user;
```

Para **restaurar**, use o **dono do banco** (ou um usuário com os mesmos privilégios): a restauração
apaga e recria os objetos. Sem permissão de leitura em alguma tabela, o `pg_dump` falha com
`permission denied` — o backup **nunca** sai incompleto em silêncio.

### MariaDB / MySQL

```sql
CREATE USER 'backup_user'@'localhost' IDENTIFIED BY 'troque-esta-senha';
GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES, EVENT ON loja.* TO 'backup_user'@'localhost';
-- para conferir/copiar procedures e functions criadas por outros usuários:
GRANT SELECT ON mysql.proc TO 'backup_user'@'localhost';
-- para também RESTAURAR pelo painel:
GRANT ALL ON loja.* TO 'backup_user'@'localhost';
```

> **Atenção (MariaDB):** sem `SELECT ON mysql.proc`, o `mariadb-dump` **omite em silêncio** as
> procedures/functions que o usuário não consegue ver — termina "com sucesso" e a cópia fica
> incompleta. O Sentinela detecta a falta dessa permissão e avisa no log e no checklist.
>
> **MySQL 8:** não existe `mysql.proc`, então a conferência de rotinas não é feita. Conceda
> `GRANT SHOW_ROUTINE ON *.* TO 'backup_user'@'localhost'` para que o dump inclua todas elas.

> Com túnel SSH, o banco enxerga a conexão como vinda do **próprio servidor** (`localhost` ou
> `127.0.0.1`). Crie o usuário para esses hosts.

---

## 8. Banco em outro servidor: túnel SSH

```mermaid
flowchart LR
    subgraph S1 [Servidor do Sentinela]
      P[pg_dump / mariadb-dump] --> L[127.0.0.1:porta aleatória]
    end
    subgraph S2 [Servidor do banco]
      D[sshd :22] --> B[(banco em localhost:5432)]
    end
    L == "túnel SSH criptografado" ==> D
```

Use quando o banco está em outro servidor e **a porta do banco não deve ficar exposta**. Só a porta
do SSH precisa estar acessível.

**Como funciona**

- A cada execução o Sentinela abre uma conexão SSH, cria uma porta local temporária
  (`127.0.0.1:<aleatória>`) que encaminha até o banco e fecha tudo ao terminar.
- O dump roda na máquina do Sentinela; as cópias ficam nela.
- **Chave do servidor (TOFU):** na primeira conexão a impressão digital do servidor SSH
  (`SHA256:…`) é registrada e exibida na tela Conexão. Se mudar depois, backups e restaurações são
  **bloqueados** (possível *man-in-the-middle* ou servidor reinstalado) até você conferir e clicar em
  **redefinir**.
- **Queda de rede:** se a conexão cair no meio do dump — inclusive quedas silenciosas, sem aviso — o
  backup falha em no máximo ~60 s com a mensagem "a conexão SSH caiu durante a transferência" e
  nenhuma cópia parcial é guardada.
- Senha SSH, chave privada e senha da chave ficam **criptografadas** no Sentinela e nunca voltam
  pela API.

**Configurando (tela Conexão → Túnel SSH)**

| Campo | Exemplo |
|---|---|
| Servidor SSH / Porta | `200.100.50.10` / `22` |
| Usuário SSH | `backup` |
| Autenticação | Senha **ou** chave privada (OpenSSH ou PEM: ed25519, RSA, ECDSA; senha da chave opcional) |
| Host / Porta do banco | `localhost` / `5432` — como o **servidor SSH** enxerga o banco |

Chaves PuTTY (`.ppk`) não são aceitas: no PuTTYgen, use *Conversions → Export OpenSSH key*.

**Recomendado no servidor do banco** — um usuário só para o túnel, sem shell, com chave:

```bash
# na máquina do Sentinela: gerar a chave
ssh-keygen -t ed25519 -f sentinela_tunel -C sentinela

# no servidor do banco: usuário dedicado
sudo useradd -m -s /usr/sbin/nologin backup
sudo install -d -m 700 -o backup -g backup /home/backup/.ssh
# em /home/backup/.ssh/authorized_keys, uma linha (a chave só abre túnel até o PostgreSQL):
restrict,port-forwarding,permitopen="localhost:5432" ssh-ed25519 AAAA...conteúdo de sentinela_tunel.pub
```

Cole o conteúdo de `sentinela_tunel` (a chave **privada**) no campo *Chave privada*. O servidor SSH
precisa permitir encaminhamento (`AllowTcpForwarding yes`, padrão do OpenSSH).

---

## 9. Linha de comando

```bash
python -m sentinela serve [--host H --port P]   # painel web + agendador
python -m sentinela passwd [usuario]             # cria usuário ou troca senha do painel
python -m sentinela backup                       # backup imediato (cron/scripts); código 0 = sucesso
python -m sentinela decrypt ARQUIVO -o SAIDA.sql [--key CHAVE]   # recupera o SQL sem o painel
python -m sentinela --version
```

Todos usam a mesma configuração do painel (`SENTINELA_HOME`). Exemplo de cron com uma cópia extra
ao meio-dia:

```cron
0 12 * * *  sentinela  cd /opt/sentinela && SENTINELA_HOME=/var/lib/sentinela .venv/bin/python -m sentinela backup
```

Se o painel já estiver executando algo, o comando termina com
`Backup não iniciado: Outro processo do Sentinela está executando…` (código ≠ 0).

---

## 10. Configuração (variáveis de ambiente)

| Variável | Padrão | Para quê |
|---|---|---|
| `SENTINELA_HOME` | `./data` | Dados da aplicação: `sentinela.db`, `sentinela.key`, `logs/` |
| `SENTINELA_BACKUP_DIR` | `/var/backups/sentinela` | Diretório padrão das cópias (alterável no painel) |
| `SENTINELA_BIND` | `127.0.0.1` | Endereço em que o painel escuta |
| `SENTINELA_PORT` | `8080` | Porta do painel |
| `SENTINELA_HTTPS` | — | `1` quando publicado atrás de proxy HTTPS (cookie *Secure* e IP real via `X-Forwarded-For`) |
| `SENTINELA_CONNECT_TIMEOUT` | `30` | Tempo máximo (s) para conectar ao banco e ao SSH |
| `SENTINELA_TICK` | `30` | Intervalo (s) de verificação do agendador |
| `SENTINELA_PG_DUMP`, `SENTINELA_PSQL` | no `PATH` | Caminho de uma versão específica dos clientes PostgreSQL |
| `SENTINELA_MYSQLDUMP`, `SENTINELA_MYSQL` | no `PATH` | Caminho dos clientes MariaDB/MySQL |

Organização em disco:

```
$SENTINELA_HOME/                  (0700 — só o usuário do serviço)
├── sentinela.db                  configurações, usuários, histórico, logs
├── sentinela.key                 chave mestra AES-256 (0600) — FAÇA UMA CÓPIA FORA DO SERVIDOR
├── sentinela.lock                trava de execução entre processos
└── logs/
    ├── sentinela.log             log geral (rotativo)
    └── execucoes/                um .log por execução

$SENTINELA_BACKUP_DIR/            (0700)
└── loja_20260929_000000.sql.gz.enc   (0600)
```

---

## 11. Recuperação de desastre

**Cenário: o servidor do Sentinela foi perdido.** Com a **chave mestra** guardada e **uma cópia**
(do disco externo, por exemplo), o banco volta — mesmo sem o painel:

```bash
# 1. recuperar o SQL (confere a autenticação GCM e o gzip no caminho)
python -m sentinela decrypt loja_20260929_000000.sql.gz.enc -o loja.sql --key sentinela.key

# 2a. PostgreSQL
psql -h servidor -U dono_do_banco -d loja -v ON_ERROR_STOP=1 --single-transaction -f loja.sql

# 2b. MariaDB
mariadb -h servidor -u usuario -p loja < loja.sql
```

Sem Python à mão? Cópias **sem** criptografia (`.sql.gz`) abrem com `gunzip`. Cópias
criptografadas exigem o Sentinela (ou qualquer implementação de AES-256-GCM seguindo o formato da
seção 4.3) **e a chave**.

> **Sem a chave mestra não há recuperação** das cópias criptografadas. Guarde-a em um cofre de
> senhas ou mídia separada — é a parte "1 cópia fora do local" da regra 3-2-1 para a própria chave.

---

## 12. Segurança

- **Cópias:** AES-256-GCM com nonce aleatório por arquivo; chave mestra separada do diretório de
  backups (quem obtém só as cópias não as lê); permissões 0600/0700; SHA-256 registrado.
- **Segredos:** senhas do banco e do SSH e chave privada SSH guardadas cifradas (AES-GCM com subchave
  derivada da chave mestra); nunca retornam pela API nem aparecem no banco SQLite em texto claro.
- **MariaDB:** a senha é passada ao cliente por arquivo temporário 0600 — não aparece no `ps`.
- **SSH:** verificação da chave do servidor (TOFU com bloqueio em caso de troca); porta local do
  túnel só em `127.0.0.1`, fechada ao fim de cada execução.
- **Painel:** senhas com hash (werkzeug/scrypt); bloqueio após 5 tentativas; sessão com cookie
  `HttpOnly` + `SameSite=Strict` (e `Secure` com HTTPS) de 8 h; CSP sem scripts inline;
  `X-Frame-Options: DENY`; sem cache nas respostas da API.
- **Execução:** gravação atômica; cópia só vira "válida" depois de relida por completo; restauração
  sempre precedida de verificação e de cópia do estado atual.

---

## 13. Solução de problemas

| Mensagem | Causa provável | O que fazer |
|---|---|---|
| `Falha na autenticação SSH (usuário, senha ou chave incorretos)` | Credencial SSH errada ou chave não autorizada | Confira usuário/senha; a chave pública precisa estar no `authorized_keys` do servidor |
| `Não foi possível conectar ao servidor SSH …: tempo esgotado` | Servidor desligado, IP errado ou firewall | Teste `ssh usuario@servidor` a partir da máquina do Sentinela |
| `…nome não encontrado (host)` | DNS não resolve o nome do servidor | Use o IP ou corrija o DNS |
| `o servidor SSH não conseguiu conectar em localhost:5432 …` | Banco parado ou host/porta errados **do ponto de vista do servidor SSH** | No servidor, rode `ss -ltn` e confira onde o banco escuta |
| `o servidor SSH não permite encaminhamento para …` | `AllowTcpForwarding no` ou `permitopen` restritivo | Libere o encaminhamento para o host/porta do banco |
| `A chave do servidor SSH mudou …` | Servidor reinstalado ou possível ataque | Confirme com o administrador; depois **redefinir** na tela Conexão |
| `a conexão SSH caiu durante a transferência …` | Rede instável ou SSH reiniciado no meio | O próximo backup tenta de novo; nenhuma cópia parcial é guardada |
| `A chave privada está protegida: informe a senha da chave` | Chave com senha | Preencha *Senha da chave* |
| `Senha da chave incorreta (ou chave corrompida)` | Senha da chave errada | Confira a senha; teste com `ssh-keygen -y -f chave` |
| `Essa é a chave pública (.pub)…` | Chave pública colada | Cole o arquivo **sem** `.pub` |
| `password authentication failed` | Senha do banco errada | Corrija na tela Conexão |
| `…insufficient privileges to SHOW CREATE… — dica: …` | Rotina de outro usuário no MariaDB | `GRANT SELECT ON mysql.proc …` (seção 7) |
| `Dump incompleto: o banco tem N procedure(s)/function(s), mas só M …` | Usuário não enxerga todas as rotinas | `GRANT SELECT ON mysql.proc …` |
| `permission denied for table …` (PostgreSQL) | Usuário sem leitura em alguma tabela | `GRANT pg_read_all_data TO …` |
| `Cliente 'pg_dump' não encontrado no servidor` | Cliente do banco não instalado | `apt install postgresql-client` / `mariadb-client` |
| `server version mismatch` (pg_dump) | `pg_dump` mais antigo que o servidor | Instale a versão do PGDG ou aponte `SENTINELA_PG_DUMP` |
| `O diretório de backup deve ficar isolado da aplicação` | Pasta dentro da aplicação ou do `SENTINELA_HOME` | Escolha outra pasta (idealmente outro disco) |
| `Hash SHA-256 diferente do registrado — arquivo alterado` | A cópia foi modificada ou corrompida no disco | Não use essa cópia; restaure outra e investigue o disco |
| `Já existe uma execução em andamento` | Outro backup/restauração rodando | Aguarde terminar (acompanhe em Logs) |

---

## 14. Testes

```bash
pip install pytest pytest-timeout
python -m pytest -q tests                 # 94 testes
```

Os testes de integração usam **bancos e servidores SSH reais**. Sem eles, são ignorados
automaticamente (os unitários continuam rodando).

| Arquivo | Cobre |
|---|---|
| `test_crypto.py` | Criptografia em fluxo, adulteração, chave errada, arquivo truncado, segredos |
| `test_engine.py` | Backup PG nas 4 combinações de proteção, adulteração, restauração PG e MariaDB, retenção, CLI `decrypt` |
| `test_web.py` | Login e bloqueio, segredos fora da API, fluxo completo, **logs ao vivo** (`/api/logs/tail`), checklist |
| `test_ssh.py` | Túnel até um sshd local (senha, chave, chave protegida, troca da chave do host) |
| `test_ssh_remote.py` | **Servidor remoto isolado** (abaixo): 56 cenários |

### Servidor remoto simulado

`tests/remote/setup.sh` (requer root) cria um **namespace de rede** Linux que se comporta como outro
servidor: IP `10.77.0.2`, `sshd` na porta 22 e PostgreSQL/MariaDB escutando **só em 127.0.0.1 lá
dentro** — a única forma de alcançá-los é pelo túnel, como numa empresa real. Também cria usuários
SSH com cenários diferentes (encaminhamento proibido, só chave, chave restrita com `permitopen`) e
sete chaves de teste (ed25519, RSA OpenSSH, RSA PEM, ECDSA, com e sem senha, não autorizada).

```bash
sudo tests/remote/setup.sh      # montar
sudo python -m pytest -q tests  # rodar tudo
sudo tests/remote/teardown.sh   # desmontar (--purge apaga os dados)
```

Cenários do `test_ssh_remote.py`:

- **Autenticação:** senha; 6 formatos de chave; chave protegida sem senha; senha da chave errada;
  chave com quebras de linha do Windows ou espaços; texto inválido e PuTTY; chave pública colada;
  chave não autorizada; senha errada; usuário inexistente; servidor que só aceita chave.
- **Rede:** porta SSH fechada; host inalcançável (tempo limite); nome que não resolve; porta do banco
  fechada no servidor; senha do banco errada; encaminhamento proibido; `permitopen` restritivo;
  host do banco resolvido **pelo servidor remoto** (`db.interno`).
- **Chave do servidor:** registro da impressão digital real; troca bloqueia teste, backup e
  restauração (banco intacto); redefinição; troca de servidor limpa a chave; teste antes de salvar.
- **Dados:** PostgreSQL de ~170 MB (200 mil OS, 180 mil eventos, view, função) e MariaDB (50 mil
  `radacct`, trigger, view, procedure, acentos UTF-8) — backup, estragos variados e restauração com
  **hash de todo o conteúdo idêntico** ao original; 4 combinações de proteção; `decrypt` pela CLI.
- **Interrupções:** sessão SSH derrubada no meio do dump; conexão do banco encerrada no meio;
  **rede cortada em silêncio** (interface desligada) — sem travar, sem cópia parcial, com a causa
  certa na mensagem, e o próximo backup funciona.
- **Recursos:** 12 ciclos seguidos sem vazar threads, arquivos ou sessões SSH; porta local do túnel
  só em loopback e liberada ao fechar.
- **Completude:** rotinas conferidas; aviso quando não dá para conferir; falha quando faltam.
- **Concorrência:** backup pelo painel bloqueia `sentinela backup` em outro processo.
- **Agendador e API:** backup automático via SSH; fluxo completo pela API; mensagens de erro.

Os testes também foram repetidos várias vezes seguidas para descartar instabilidade, e o painel foi
exercitado de ponta a ponta num navegador real (Playwright): login, configuração do túnel com chave
protegida, backups, terminal ao vivo, filtros, busca, verificação, restauração, tema escuro e
layout de celular.

---

## 15. Estrutura do código e API

```
sentinela/
├── __main__.py    linha de comando (serve, passwd, backup, decrypt)
├── engine.py      backup, verificação, restauração, retenção, logs, progresso, travas
├── dumpers.py     adaptadores PostgreSQL e MariaDB, pré-verificação, dicas de permissão
├── tunnel.py      túnel SSH (paramiko): chave do host, encaminhamento, detecção de queda
├── crypto.py      AES-256-GCM em fluxo, chave mestra, segredos
├── scheduler.py   agendador (diário/intervalo) e limpeza periódica
├── storage.py     SQLite
├── settings.py    caminhos e limites
├── web.py         API JSON, checklist de saúde, cabeçalhos de segurança
└── static/        painel: HTML/CSS/JS puro (sem build), fontes IBM Plex locais
tests/             unitários e integração (bancos e SSH reais) + tests/remote/ (servidor simulado)
deploy/            serviço systemd
docs/img/          capturas de tela
```

Endpoints (todos exigem sessão, exceto login):

| Método | Rota | Função |
|---|---|---|
| POST | `/api/login` · `/api/logout` | Sessão |
| GET | `/api/state` | Estado geral, execução em andamento, gráfico, checklist |
| PUT | `/api/policy` | Salvar política |
| PUT | `/api/connection` · POST `/api/connection/test` | Salvar / testar conexão (e túnel SSH) |
| GET · POST | `/api/backups` | Listar cópias / iniciar backup manual |
| GET · DELETE | `/api/backups/<id>` | Detalhe com log / excluir |
| POST | `/api/backups/<id>/verify` · `/restore` | Verificar / restaurar |
| GET | `/api/backups/<id>/download` | Baixar a cópia (criptografada) |
| GET | `/api/logs` · `/api/logs/tail?since=<id>` · `/api/logs/download` | Execuções, linhas novas (ao vivo), arquivo |
| GET | `/api/executions/<id>` | Uma execução com suas linhas |

---

## 16. Limitações conhecidas

- **Backup lógico completo** a cada execução (dump SQL). Não há backup incremental nem PITR; para
  bases muito grandes (centenas de GB) um backup físico (ex.: `pg_basebackup`) é mais adequado.
- **Um banco por instalação.** Para vários bancos, rode uma instância por banco (outro
  `SENTINELA_HOME` e outra porta).
- **Restauração do MariaDB não é atômica** (limitação do próprio cliente); a cópia pré-restauração
  cobre esse caso.
- Horários (agendamento e logs) usam o **fuso do servidor**.
- Testado em Linux. macOS deve funcionar com os clientes do Homebrew, mas não foi testado;
  Windows apenas via WSL.

---

<sub>Projeto Integrador — Curso Técnico · IFSC Câmpus São Lourenço do Oeste · 2026 · Licença MIT</sub>
