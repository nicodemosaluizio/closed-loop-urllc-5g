#!/usr/bin/env python3
"""
Closed Loop dinamico - peca final do projeto.

Fluxo:
 1. Sobe a topologia diamante
 2. Aplica a estrutura de filas QoS (uRLLC/eMBB) em modo neutro
    (banda dividida igualmente entre as duas classes)
 3. Liga os servidores em h2 (OWD + iperf3)
 4. Inicia a sonda uRLLC (h1) continuamente, em background
 5. Fase de CALIBRACAO: mede o baseline real da latencia (ferramenta
    de medicao + rede), sem trafego eMBB
 6. Inicia o LOOP DE CONTROLE em uma thread separada: mede a
    DEGRADACAO (latencia atual - baseline) a cada 1s e ajusta
    dinamicamente as taxas das filas sempre que a degradacao
    ultrapassa o limiar de 5ms do PDF. Quando a degradacao volta
    ao normal, o sistema recua para um nivel menos agressivo.
 7. Dispara uma rajada de eMBB para gerar congestionamento de teste
 8. Registra cada ajuste de nivel em /tmp/eventos_closed_loop.csv

Uso:
    sudo python3 closed_loop_dinamico.py [--duracao SEG] [--calibracao SEG] [--embb SEG]
"""

import argparse
import csv
import os
import threading
import time

from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info

from topologia_diamante import RoutedTopo, config_ips, enable_forwarding, config_routes
from qos_priorizacao import aplicar_qos, remover_qos, ajustar_taxa_fila

ARQ_OWD = '/tmp/owd_urllc.csv'
ARQ_EVENTOS = '/tmp/eventos_closed_loop.csv'

INTERFACES_ROTA_A = ['r1-eth1', 'r2-eth1']
BANDA_LINK_MBIT = 10

LIMIAR_DEGRADACAO_MS = 5.0   # requisito do PDF: degradacao maxima tolerada
JANELA_AMOSTRAS = 5           # amostras recentes usadas na media
INTERVALO_CONTROLE = 1.0      # segundos entre decisoes do loop

# Niveis de atuacao: (rate_embb_mbit, rate_urllc_mbit) - soma sempre = 10
NIVEIS = [
    (5, 5),   # nivel 0: neutro
    (3, 7),   # nivel 1: prioridade leve ao uRLLC
    (1, 9),   # nivel 2: prioridade forte ao uRLLC
]


def limpar_arquivos():
    for caminho in (ARQ_OWD, '/tmp/servidor.log', ARQ_EVENTOS):
        if os.path.exists(caminho):
            os.remove(caminho)


def ler_ultimas_amostras(caminho, n):
    if not os.path.exists(caminho):
        return []
    with open(caminho) as f:
        linhas = list(csv.reader(f))[1:]
    valores = []
    for _ts, owd in reversed(linhas):
        if owd != '':
            try:
                valores.append(float(owd))
            except ValueError:
                continue
        if len(valores) >= n:
            break
    return list(reversed(valores))


def calibrar_baseline(duracao):
    """Aguarda 'duracao' segundos de trafego uRLLC (sem eMBB) e mede o baseline."""
    info(f'*** Calibrando baseline por {duracao}s (sem eMBB)...\n')
    time.sleep(duracao)
    amostras = ler_ultimas_amostras(ARQ_OWD, 20)
    if not amostras:
        info('*** AVISO: sem amostras de calibracao, usando baseline padrao de 7ms\n')
        return 7.0
    baseline = sum(amostras) / len(amostras)
    info(f'*** Baseline calibrado: {baseline:.2f} ms ({len(amostras)} amostras)\n')
    return baseline


def loop_controle(net, baseline, parar_evento, arquivo_eventos):
    """Thread de controle: ajusta as filas dinamicamente com base na degradacao medida."""
    writer = csv.writer(arquivo_eventos)
    writer.writerow(['timestamp', 'nivel', 'latencia_media_ms', 'baseline_ms', 'degradacao_ms', 'motivo'])
    arquivo_eventos.flush()

    nivel_atual = 0

    while not parar_evento.is_set():
        amostras = ler_ultimas_amostras(ARQ_OWD, JANELA_AMOSTRAS)
        if amostras:
            media = sum(amostras) / len(amostras)
            degradacao = media - baseline

            novo_nivel = nivel_atual
            motivo = None

            if degradacao > LIMIAR_DEGRADACAO_MS and nivel_atual < len(NIVEIS) - 1:
                novo_nivel = nivel_atual + 1
                motivo = f'degradacao {degradacao:.2f}ms > limiar {LIMIAR_DEGRADACAO_MS}ms'
            elif degradacao < LIMIAR_DEGRADACAO_MS / 2 and nivel_atual > 0:
                novo_nivel = nivel_atual - 1
                motivo = f'degradacao {degradacao:.2f}ms normalizada, recuando'

            if novo_nivel != nivel_atual:
                rate_embb, rate_urllc = NIVEIS[novo_nivel]
                ajustar_taxa_fila(net, INTERFACES_ROTA_A, '1:20', rate_embb, BANDA_LINK_MBIT)
                ajustar_taxa_fila(net, INTERFACES_ROTA_A, '1:10', rate_urllc, BANDA_LINK_MBIT)

                writer.writerow([time.time(), novo_nivel, round(media, 3),
                                  round(baseline, 3), round(degradacao, 3), motivo])
                arquivo_eventos.flush()

                info(f'\n[CLOSED LOOP] Nivel {nivel_atual} -> {novo_nivel} | '
                     f'lat_media={media:.2f}ms degradacao={degradacao:.2f}ms | {motivo}\n\n')
                nivel_atual = novo_nivel

        time.sleep(INTERVALO_CONTROLE)


def main():
    setLogLevel('info')
    parser = argparse.ArgumentParser(description='Closed Loop dinamico uRLLC x eMBB')
    parser.add_argument('--duracao', type=int, default=50, help='Duracao total da sonda uRLLC (s)')
    parser.add_argument('--calibracao', type=int, default=6, help='Duracao da fase de calibracao (s)')
    parser.add_argument('--embb', type=int, default=25, help='Duracao da rajada eMBB (s)')
    args = parser.parse_args()

    limpar_arquivos()

    topo = RoutedTopo()
    net = Mininet(topo=topo, link=TCLink, controller=None)
    net.start()

    config_ips(net)
    enable_forwarding(net)
    config_routes(net, active_route='A')

    info('*** Aplicando estrutura de QoS (nivel neutro inicial)\n')
    aplicar_qos(net, INTERFACES_ROTA_A, banda_mbit=BANDA_LINK_MBIT)
    rate_embb0, rate_urllc0 = NIVEIS[0]
    ajustar_taxa_fila(net, INTERFACES_ROTA_A, '1:20', rate_embb0, BANDA_LINK_MBIT)
    ajustar_taxa_fila(net, INTERFACES_ROTA_A, '1:10', rate_urllc0, BANDA_LINK_MBIT)

    h1, h2 = net.get('h1', 'h2')

    info('*** Iniciando servidores em h2 (OWD + iperf3)\n')
    h2.cmd('python3 servidor_urllc.py --iface h2-eth0 > /tmp/servidor.log 2>&1 &')
    h2.cmd('iperf3 -s -p 5201 > /tmp/iperf_servidor.log 2>&1 &')
    time.sleep(1)

    info(f'*** Iniciando sonda uRLLC em h1 por {args.duracao}s\n')
    h1.cmd(f'timeout {args.duracao} python3 sonda_urllc.py 10.0.6.2 --iface h1-eth0 '
           f'> /tmp/sonda.log 2>&1 &')

    baseline = calibrar_baseline(args.calibracao)

    arquivo_eventos = open(ARQ_EVENTOS, 'w', newline='')
    parar_evento = threading.Event()
    thread_controle = threading.Thread(
        target=loop_controle, args=(net, baseline, parar_evento, arquivo_eventos), daemon=True
    )
    thread_controle.start()

    info(f'*** Disparando trafego eMBB por {args.embb}s...\n')
    saida_embb = h1.cmd(f'iperf3 -c 10.0.6.2 -p 5201 -t {args.embb}')
    info('*** Trafego eMBB finalizado\n')

    ja_passado = args.calibracao + args.embb
    tempo_restante = args.duracao - ja_passado
    if tempo_restante > 0:
        info(f'*** Aguardando mais {tempo_restante:.1f}s para observar a recuperacao...\n')
        time.sleep(tempo_restante)

    parar_evento.set()
    thread_controle.join(timeout=2)
    arquivo_eventos.close()

    remover_qos(net, INTERFACES_ROTA_A)

    info('*** Closed Loop dinamico concluido.\n')
    info(f'*** Latencia OWD salva em: {ARQ_OWD}\n')
    info(f'*** Eventos de ajuste salvos em: {ARQ_EVENTOS}\n')
    info('--- Resumo do iperf3 (eMBB) ---\n')
    info(saida_embb + '\n')

    net.stop()


if __name__ == '__main__':
    main()
