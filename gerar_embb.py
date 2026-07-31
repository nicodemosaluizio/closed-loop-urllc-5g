#!/usr/bin/env python3
"""
Gerador de trafego eMBB - roda dentro de h1.

Usa iperf3 para gerar trafego TCP de alta largura de banda,
simulando uma aplicacao eMBB (ex: streaming/transferencia de
arquivo). Esse trafego satura os links de transporte (10mbit),
criando congestionamento real que disputa espaco com o trafego
uRLLC concorrente na mesma rota.

Pre-requisito: um servidor iperf3 precisa estar rodando no destino
(ex: dentro de h2, comando: iperf3 -s)

Uso:
    python3 gerar_embb.py <ip_destino> [--duracao SEG] [--banda TAXA] [--porta PORTA]

Exemplo:
    python3 gerar_embb.py 10.0.6.2 --duracao 30
"""

import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser(description='Gerador de trafego eMBB via iperf3')
    parser.add_argument('destino', help='IP do servidor iperf3 (ex: 10.0.6.2)')
    parser.add_argument('--duracao', type=int, default=30, help='Duracao da rajada eMBB (segundos)')
    parser.add_argument('--banda', default=None, help="Taxa alvo (ex: '20M'). Se omitido, TCP tenta usar toda banda disponivel")
    parser.add_argument('--porta', type=int, default=5201, help='Porta do servidor iperf3')
    args = parser.parse_args()

    comando = ['iperf3', '-c', args.destino, '-p', str(args.porta), '-t', str(args.duracao)]
    if args.banda:
        comando += ['-b', args.banda]

    print('Executando:', ' '.join(comando))
    subprocess.run(comando)


if __name__ == '__main__':
    main()
