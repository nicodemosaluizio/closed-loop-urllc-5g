#!/usr/bin/env python3
"""
Executa um experimento controlado uRLLC x eMBB, do inicio ao fim,
em um UNICO processo Python - sem depender de comandos manuais
digitados em sequencia no CLI do Mininet.

Fluxo:
  1. Sobe a topologia diamante
  2. (Opcional) Aplica QoS de prioridade (uRLLC > eMBB) nos enlaces
     de transporte da rota ativa
  3. Liga os servidores em h2 (medicao de OWD + iperf3)
  4. Inicia a sonda uRLLC em h1, rodando em segundo plano
  5. Aguarda um periodo de baseline (sem eMBB)
  6. Dispara uma rajada de trafego eMBB (iperf3) e registra o
     horario EXATO de inicio/fim
  7. Aguarda a sonda terminar e finaliza

Uso:
    sudo python3 rodar_experimento.py [--duracao SEG] [--espera SEG] [--embb SEG] [--qos]

Exemplos:
    # Cenario SEM QoS (baseline do problema)
    sudo python3 rodar_experimento.py --duracao 40 --espera 8 --embb 20

    # Cenario COM QoS (solucao aplicada)
    sudo python3 rodar_experimento.py --duracao 40 --espera 8 --embb 20 --qos
"""

import argparse
import json
import os
import time

from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info

from topologia_diamante import RoutedTopo, config_ips, enable_forwarding, config_routes
from qos_priorizacao import aplicar_qos, remover_qos

ARQ_OWD = '/tmp/owd_urllc.csv'
ARQ_EVENTOS = '/tmp/eventos_embb.json'

# Interfaces de saida da Rota A (r1 -> r2 -> r4), sentido h1 -> h2
INTERFACES_ROTA_A = ['r1-eth1', 'r2-eth1']


def limpar_arquivos():
    for caminho in (ARQ_OWD, '/tmp/servidor.log', '/tmp/sonda.log', ARQ_EVENTOS):
        if os.path.exists(caminho):
            os.remove(caminho)


def main():
    setLogLevel('info')
    parser = argparse.ArgumentParser(description='Executa experimento uRLLC x eMBB')
    parser.add_argument('--duracao', type=int, default=40, help='Duracao total da sonda uRLLC (s)')
    parser.add_argument('--espera', type=int, default=8, help='Segundos de baseline antes do eMBB (s)')
    parser.add_argument('--embb', type=int, default=20, help='Duracao da rajada eMBB (s)')
    parser.add_argument('--qos', action='store_true', help='Aplica priorizacao uRLLC > eMBB nos enlaces de transporte')
    args = parser.parse_args()

    limpar_arquivos()

    topo = RoutedTopo()
    net = Mininet(topo=topo, link=TCLink, controller=None)
    net.start()

    config_ips(net)
    enable_forwarding(net)
    config_routes(net, active_route='A')

    if args.qos:
        info('*** Aplicando QoS (uRLLC prioridade alta, eMBB prioridade baixa)\n')
        aplicar_qos(net, INTERFACES_ROTA_A, banda_mbit=10)
    else:
        info('*** Rodando SEM QoS (fila unica, sem priorizacao) - cenario baseline\n')

    h1, h2 = net.get('h1', 'h2')

    info('*** Iniciando servidores em h2 (OWD + iperf3)\n')
    h2.cmd('python3 servidor_urllc.py --iface h2-eth0 > /tmp/servidor.log 2>&1 &')
    h2.cmd('iperf3 -s -p 5201 > /tmp/iperf_servidor.log 2>&1 &')
    time.sleep(1)  # da tempo dos servidores subirem

    info(f'*** Iniciando sonda uRLLC em h1 por {args.duracao}s\n')
    h1.cmd(f'timeout {args.duracao} python3 sonda_urllc.py 10.0.6.2 --iface h1-eth0 '
           f'> /tmp/sonda.log 2>&1 &')

    info(f'*** Aguardando {args.espera}s de baseline (sem eMBB)...\n')
    time.sleep(args.espera)

    t_inicio_embb = time.time()
    info(f'*** Disparando trafego eMBB por {args.embb}s...\n')
    saida_embb = h1.cmd(f'iperf3 -c 10.0.6.2 -p 5201 -t {args.embb}')
    t_fim_embb = time.time()
    info('*** Trafego eMBB finalizado\n')

    eventos = {
        'qos_ativo': args.qos,
        'inicio_embb': t_inicio_embb,
        'fim_embb': t_fim_embb,
        'duracao_embb_real': round(t_fim_embb - t_inicio_embb, 3),
    }
    with open(ARQ_EVENTOS, 'w') as f:
        json.dump(eventos, f, indent=2)

    ja_passado = args.espera + args.embb
    tempo_restante = args.duracao - ja_passado
    if tempo_restante > 0:
        info(f'*** Aguardando mais {tempo_restante:.1f}s ate a sonda terminar...\n')
        time.sleep(tempo_restante)

    if args.qos:
        remover_qos(net, INTERFACES_ROTA_A)

    info('*** Experimento concluido.\n')
    info(f'*** Latencia OWD salva em: {ARQ_OWD}\n')
    info(f'*** Janela do eMBB salva em: {ARQ_EVENTOS}\n')
    info('--- Resumo do iperf3 (eMBB) ---\n')
    info(saida_embb + '\n')

    net.stop()


if __name__ == '__main__':
    main()
