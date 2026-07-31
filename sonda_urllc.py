#!/usr/bin/env python3
"""
Sonda uRLLC (OWD) - roda dentro de h1.

Envia pacotes TCP para o servidor (h2), com o timestamp exato de
envio embutido no payload (via Scapy). NAO espera resposta - a
medicao de OWD (One-Way Delay, atraso fim-a-fim conforme o PDF)
e feita inteiramente do lado do servidor, que calcula:

    OWD = timestamp_chegada - timestamp_envio (embutido no pacote)

Uso:
    python3 sonda_urllc.py <ip_destino> [--porta PORTA] [--intervalo SEG] [--iface IFACE]
"""

import argparse
import time

from scapy.all import IP, TCP, Raw, conf

conf.verb = 0


def main():
    parser = argparse.ArgumentParser(description='Sonda uRLLC - envio para medicao de OWD (Scapy)')
    parser.add_argument('destino', help='IP de destino (ex: 10.0.6.2)')
    parser.add_argument('--porta', type=int, default=9000, help='Porta TCP de destino')
    parser.add_argument('--intervalo', type=float, default=0.2, help='Intervalo entre envios (s)')
    parser.add_argument('--iface', default=None, help='Interface de rede (ex: h1-eth0)')
    args = parser.parse_args()

    sock = conf.L3socket(iface=args.iface)

    print(f'Enviando sondas uRLLC (OWD) para {args.destino}:{args.porta}...')
    try:
        while True:
            porta_origem = 40000 + int(time.time() * 1000) % 10000
            timestamp_envio = f'{time.time():.6f}'.encode()
            pacote = (
                IP(dst=args.destino)
                / TCP(sport=porta_origem, dport=args.porta, flags='PA')
                / Raw(load=timestamp_envio)
            )
            sock.send(pacote)
            time.sleep(args.intervalo)
    finally:
        sock.close()


if __name__ == '__main__':
    main()
