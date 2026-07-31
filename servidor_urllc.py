#!/usr/bin/env python3
"""
Servidor uRLLC (OWD) - roda dentro de h2.

OTIMIZACAO: em vez de sniff() (que adiciona compilacao de filtro BPF,
gerenciamento de buffer/store e overhead de conveniencia por pacote),
usa diretamente o socket L2 de baixo nivel do proprio Scapy
(conf.L2listen()) num loop de recv() manual. Continua sendo 100%
Scapy (mesma biblioteca, mesma decodificacao de pacotes como objetos
IP/TCP/Raw) - so pula a camada de conveniencia do sniff(), reduzindo
o overhead de processamento por pacote. Tambem evita print() e writes
em disco a cada pacote (I/O e caro), fazendo flush a cada 10 amostras.

Uso:
    python3 servidor_urllc.py [--iface IFACE] [--porta PORTA] [--out ARQUIVO]
"""

import argparse
import csv
import os
import time

from scapy.all import IP, TCP, Raw, conf

conf.verb = 0


def main():
    parser = argparse.ArgumentParser(description='Servidor uRLLC - OWD via socket L2 do Scapy (sem sniff)')
    parser.add_argument('--iface', default=None, help='Interface de rede (ex: h2-eth0)')
    parser.add_argument('--porta', type=int, default=9000, help='Porta TCP monitorada')
    parser.add_argument('--out', default='/tmp/owd_urllc.csv', help='Arquivo CSV de saida')
    args = parser.parse_args()

    novo_arquivo = not os.path.exists(args.out)
    arquivo = open(args.out, 'a', newline='')
    writer = csv.writer(arquivo)
    if novo_arquivo:
        writer.writerow(['timestamp_chegada', 'owd_ms'])

    # Socket L2 de baixo nivel do proprio Scapy - ainda e Scapy,
    # so sem a camada de conveniencia do sniff()
    sock = conf.L2listen(iface=args.iface)

    print(f'Servidor uRLLC (OWD) escutando na porta {args.porta} (iface={args.iface})...')
    print('[socket L2 do Scapy, sem sniff() - modo otimizado]')

    contador = 0
    try:
        while True:
            pkt = sock.recv()
            t_chegada = time.time()

            if pkt is None:
                continue
            if TCP not in pkt or Raw not in pkt:
                continue
            if pkt[TCP].dport != args.porta:
                continue

            try:
                t_envio = float(pkt[Raw].load.decode())
            except (ValueError, UnicodeDecodeError):
                continue

            owd_ms = round((t_chegada - t_envio) * 1000, 3)
            writer.writerow([t_chegada, owd_ms])
            contador += 1
            if contador % 10 == 0:
                arquivo.flush()
    except KeyboardInterrupt:
        pass
    finally:
        arquivo.flush()
        arquivo.close()
        sock.close()


if __name__ == '__main__':
    main()
