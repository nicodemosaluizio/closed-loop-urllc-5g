# Sistema de Monitoramento e Controle *Closed Loop* para Aplicações uRLLC em Redes de Transporte 5G

Projeto Final — Disciplina de Redes de Computadores
Mestrado em Tecnologia da Informação (PPGTI) — IFPB Campus João Pessoa
Profs. Paulo Ditarso Maciel Jr. e Leandro Almeida

## 1. Sobre o projeto

Este projeto implementa e avalia um sistema de *Closed Loop* (ciclo de monitoramento,
decisão e atuação) capaz de manter a latência fim-a-fim de tráfego **uRLLC**
(*Ultra-Reliable Low Latency Communication*) abaixo de um limiar de degradação de
**5ms**, mesmo quando a rede está sob congestionamento causado por tráfego **eMBB**
(*enhanced Mobile Broadband*) concorrente.

Toda a rede de transporte é emulada em uma topologia **diamante com 4 roteadores**,
com dois caminhos possíveis entre origem e destino. O sistema monitora continuamente a
latência do tráfego uRLLC e, ao detectar degradação acima do limiar, ajusta
dinamicamente a priorização das filas de rede para proteger o tráfego sensível à
latência — sem qualquer intervenção manual.

O artigo científico completo, com a descrição detalhada da metodologia, da proposta e
da avaliação experimental, está em [`artigo_closed_loop.tex`](./artigo_closed_loop.tex).

## 2. Tecnologias e ferramentas utilizadas

| Ferramenta | Papel no projeto |
|---|---|
| **Mininet 2.3.0** | Emulação de toda a topologia de rede (hosts, roteadores, enlaces) usando *namespaces* de rede Linux |
| **Scapy** | Geração e medição do tráfego uRLLC via pacotes TCP crafted manualmente (envio e captura) |
| **iperf3** | Geração de tráfego eMBB de alto volume, simulando aplicações de banda larga |
| **Linux `tc` / HTB** (*Hierarchical Token Bucket*) | Implementação das filas de prioridade e do controle de banda dinâmico nos roteadores |
| **Python 3** | Linguagem de implementação de todos os scripts (topologia, sondas, controle) |
| **Matplotlib** | Geração dos gráficos comparativos de latência para o artigo |

Sistema operacional utilizado no desenvolvimento e nos testes: **Ubuntu 22.04 LTS**.

## 3. Estrutura do repositório

```
.
├── topologia_diamante.py     # Topologia Mininet (4 roteadores, IP forwarding, rotas)
├── servidor_urllc.py         # Servidor uRLLC (h2): mede OWD via Scapy (socket L2)
├── sonda_urllc.py             # Sonda uRLLC (h1): envia pacotes TCP com timestamp via Scapy
├── gerar_embb.py               # Gerador de trafego eMBB (h1): dispara trafego via iperf3
├── qos_priorizacao.py         # Modulo de QoS: cria e ajusta filas HTB com prioridade
├── rodar_experimento.py       # Experimento automatizado: cenarios COM/SEM QoS estatico
├── closed_loop_dinamico.py    # Script principal: Closed Loop completo e dinamico
├── analisar_resultados.py     # Analise estatistica + geracao de graficos comparativos
├── artigo_closed_loop.tex     # Artigo cientifico completo (template SBC)
└── README.md                  # Este arquivo
```

## 4. Pré-requisitos

Testado em **Ubuntu 22.04 LTS**. Instale as dependências com:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y mininet iperf3 iproute2 net-tools python3 python3-pip
sudo pip3 install scapy --break-system-packages
sudo pip3 install matplotlib --break-system-packages
```

Verifique se tudo foi instalado corretamente:

```bash
sudo mn --version          # deve mostrar 2.3.0 ou superior
python3 -c "import scapy; print(scapy.VERSION)"
iperf3 --version
```

## 5. Passo a passo de execução

> **Importante:** todos os comandos abaixo devem ser executados dentro da pasta do
> projeto, com todos os arquivos `.py` listados na Seção 3 presentes no mesmo diretório
> (os scripts se importam entre si).

### 5.1 Limpar o ambiente antes de qualquer execução

O Mininet pode deixar resíduos de execuções anteriores (namespaces, interfaces
virtuais). Antes de qualquer teste, rode:

```bash
sudo mn -c
```

### 5.2 Validar a topologia isoladamente (opcional, recomendado na primeira vez)

Sobe a rede sozinha, testa conectividade e abre o CLI interativo do Mininet para
exploração manual:

```bash
sudo python3 topologia_diamante.py
```

Dentro do CLI, você pode testar:

```
mininet> h1 ping -c 3 h2
mininet> py __import__('__main__').set_active_route(net, "B")
mininet> h1 ping -c 3 h2
mininet> exit
```

Isso confirma que as duas rotas (A via `r2`, B via `r3`) têm conectividade e latências
distintas.

### 5.3 Reproduzir o experimento comparativo (Sem QoS × Com QoS estático)

Este passo reproduz os resultados das Seções 4.1 e 4.2 do artigo — o efeito do
congestionamento sem nenhum controle, e o efeito da priorização de filas fixa.

**Cenário 1 — Sem QoS (baseline do problema):**

```bash
sudo mn -c
sudo python3 rodar_experimento.py --duracao 40 --espera 8 --embb 20
cp /tmp/owd_urllc.csv resultado_sem_qos.csv
cp /tmp/eventos_embb.json eventos_sem_qos.json
```

**Cenário 2 — Com QoS estático (priorização fixa):**

```bash
sudo mn -c
sudo python3 rodar_experimento.py --duracao 40 --espera 8 --embb 20 --qos
cp /tmp/owd_urllc.csv resultado_com_qos.csv
cp /tmp/eventos_embb.json eventos_com_qos.json
```

**Parâmetros disponíveis** em `rodar_experimento.py`:

| Parâmetro | Descrição | Padrão |
|---|---|---|
| `--duracao` | Duração total da sonda uRLLC (segundos) | 40 |
| `--espera` | Segundos de baseline antes de iniciar o eMBB | 8 |
| `--embb` | Duração da rajada de tráfego eMBB (segundos) | 20 |
| `--qos` | Ativa a priorização de filas fixa (flag, sem valor) | desativado |

### 5.4 Gerar a análise estatística e os gráficos comparativos

Depois de rodar os dois cenários acima e salvar os arquivos `resultado_*.csv` /
`eventos_*.json`, gere o resumo estatístico e o gráfico comparativo:

```bash
python3 analisar_resultados.py
```

Isso imprime no terminal a latência média antes/durante/depois do eMBB em cada
cenário, e salva o gráfico em `latencia_comparacao.png`.

### 5.5 Reproduzir o Closed Loop dinâmico (mecanismo completo)

Este é o experimento principal do projeto (Seção 4.3 do artigo): o sistema calibra o
baseline automaticamente, monitora a latência continuamente, e ajusta as filas de
prioridade em tempo real, sem intervenção manual.

```bash
sudo mn -c
sudo python3 closed_loop_dinamico.py --duracao 50 --calibracao 6 --embb 25
```

Acompanhe a saída no terminal: mensagens como `[CLOSED LOOP] Nivel 0 -> 1 | ...`
aparecem em tempo real, mostrando o sistema detectando a degradação e reagindo
sozinho. Ao final, os arquivos gerados são:

- `/tmp/owd_urllc.csv` — série completa de latência (OWD) medida durante o experimento
- `/tmp/eventos_closed_loop.csv` — registro de cada mudança de nível de atuação
  (timestamp, nível anterior/novo, latência média, degradação, motivo)

**Parâmetros disponíveis** em `closed_loop_dinamico.py`:

| Parâmetro | Descrição | Padrão |
|---|---|---|
| `--duracao` | Duração total da sonda uRLLC (segundos) | 50 |
| `--calibracao` | Duração da fase de calibração do baseline (segundos) | 6 |
| `--embb` | Duração da rajada de tráfego eMBB (segundos) | 25 |

## 6. Como interpretar os resultados

A métrica principal utilizada na avaliação **não é o valor absoluto de latência**, e
sim a **degradação em relação ao baseline calibrado** (`latência atual − baseline`).
Isso ocorre porque a própria ferramenta de medição (Python + Scapy) introduz um
*overhead* de processamento de aproximadamente 5 a 8ms, mesmo em uma rede sem
congestionamento algum — essa limitação está detalhada na Seção 2.3.1 do artigo. Ou
seja: o requisito de 5ms do projeto é avaliado como *quanto o congestionamento pode
aumentar a latência antes que o sistema reaja*, não como um valor absoluto de RTT/OWD
medido pela sonda.

## 7. Limitações conhecidas

- O *baseline* de latência medido (5–8ms) reflete o custo computacional da ferramenta
  de medição em Python/Scapy, não a latência real da rede emulada.
- Os resultados reportados no artigo refletem execuções únicas de cada cenário, não
  médias estatísticas de múltiplas repetições.
- A capacidade de redirecionamento de rota (Rota A/B, ver `topologia_diamante.py`,
  função `set_active_route()`) foi implementada e validada isoladamente, mas não está
  integrada ao `closed_loop_dinamico.py` nesta versão — apenas a priorização de filas é
  usada como mecanismo de atuação no Closed Loop avaliado no artigo.

Discussão completa dessas limitações na Seção 4.6 do artigo (*"Síntese do
desenvolvimento: sucessos, desafios e limitações"*).

## 8. Autor

Aluízio Nicodemos — PPGTI, IFPB Campus João Pessoa
