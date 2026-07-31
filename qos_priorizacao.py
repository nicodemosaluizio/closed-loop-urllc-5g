#!/usr/bin/env python3
"""
Modulo de QoS - fila com prioridade para trafego uRLLC.

Implementa o requisito central do PDF: usa filtros (por porta TCP) para
mapear o trafego uRLLC (porta 9000) para uma classe de ALTA prioridade,
e o trafego eMBB (porta 5201) para uma classe de prioridade inferior,
dentro dos enlaces de transporte (10mbit) que sao o gargalo da rede.

Estrutura HTB criada em cada interface:

    1: (raiz, rate = banda total do link)
      |
      +-- 1:10  uRLLC  (prio 0 - atendida primeiro, sempre que tiver pacote)
      +-- 1:20  eMBB   (prio 1 - atendida depois, pega o que sobrar)

Uso tipico:
    from qos_priorizacao import aplicar_qos, remover_qos, ajustar_taxa_fila
    aplicar_qos(net, ['r1-eth1', 'r1-eth2'])
    ajustar_taxa_fila(net, ['r1-eth1'], classid='1:20', rate_mbit=3, ceil_mbit=10)
"""

from mininet.log import info

PORTA_URLLC = 9000
PORTA_EMBB = 5201


def aplicar_qos(net, interfaces, banda_mbit=10):
    """
    Aplica filas de prioridade (uRLLC > eMBB) nas interfaces informadas.
    interfaces: lista de nomes (ex: ['r1-eth1', 'r1-eth2'])
    """
    for nome_if in interfaces:
        no = _encontrar_no_da_interface(net, nome_if)
        if no is None:
            info(f'*** [QoS] Interface {nome_if} nao encontrada, pulando\n')
            continue

        # Remove qualquer qdisc anterior (inclusive o padrao criado pelo Mininet)
        no.cmd(f'tc qdisc del dev {nome_if} root 2>/dev/null')

        # Raiz HTB - classe default (1:20 = eMBB) para trafego nao filtrado
        no.cmd(f'tc qdisc add dev {nome_if} root handle 1: htb default 20')

        # Classe pai, limita o link a banda total do enlace
        no.cmd(f'tc class add dev {nome_if} parent 1: classid 1:1 '
               f'htb rate {banda_mbit}mbit ceil {banda_mbit}mbit')

        # Classe uRLLC: prioridade 0 (mais alta), pode usar ate 100% do link
        no.cmd(f'tc class add dev {nome_if} parent 1:1 classid 1:10 '
               f'htb rate 2mbit ceil {banda_mbit}mbit prio 0')
        no.cmd(f'tc qdisc add dev {nome_if} parent 1:10 handle 10: pfifo limit 10')

        # Classe eMBB: prioridade 1 (mais baixa), pega o que sobrar
        no.cmd(f'tc class add dev {nome_if} parent 1:1 classid 1:20 '
               f'htb rate {max(banda_mbit - 2, 1)}mbit ceil {banda_mbit}mbit prio 1')
        no.cmd(f'tc qdisc add dev {nome_if} parent 1:20 handle 20: pfifo limit 50')

        # Filtros: classificam o pacote pela porta TCP de destino
        no.cmd(f'tc filter add dev {nome_if} parent 1: protocol ip prio 1 u32 '
               f'match ip dport {PORTA_URLLC} 0xffff flowid 1:10')
        no.cmd(f'tc filter add dev {nome_if} parent 1: protocol ip prio 2 u32 '
               f'match ip dport {PORTA_EMBB} 0xffff flowid 1:20')

        info(f'*** [QoS] Prioridade aplicada em {nome_if} '
             f'(uRLLC=alta prioridade, eMBB=baixa prioridade)\n')


def ajustar_taxa_fila(net, interfaces, classid, rate_mbit, ceil_mbit):
    """
    Altera dinamicamente a taxa de uma classe HTB JA EXISTENTE, sem
    recriar toda a estrutura de filas do zero (tc class change).

    Esta e a funcao que o Closed Loop dinamico chama em tempo real
    para reagir a degradacao de latencia: reduz a taxa da fila eMBB
    (classid 1:20) e/ou aumenta a da fila uRLLC (classid 1:10).
    """
    for nome_if in interfaces:
        no = _encontrar_no_da_interface(net, nome_if)
        if no is None:
            continue
        no.cmd(f'tc class change dev {nome_if} parent 1:1 classid {classid} '
               f'htb rate {rate_mbit}mbit ceil {ceil_mbit}mbit')


def remover_qos(net, interfaces):
    """Remove a configuracao de QoS, voltando ao qdisc padrao (sem prioridade)."""
    for nome_if in interfaces:
        no = _encontrar_no_da_interface(net, nome_if)
        if no is None:
            continue
        no.cmd(f'tc qdisc del dev {nome_if} root 2>/dev/null')
        info(f'*** [QoS] Prioridade removida de {nome_if}\n')


def _encontrar_no_da_interface(net, nome_if):
    """Descobre qual no do Mininet possui a interface com esse nome (ex: r1-eth1 -> r1)."""
    prefixo = nome_if.split('-')[0]
    try:
        return net.get(prefixo)
    except KeyError:
        return None
