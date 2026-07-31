#!/usr/bin/env python3
"""
Topologia Diamante com 4 roteadores para o projeto Closed Loop uRLLC/eMBB.

Estrutura:

    h1 --- r1 --- r2 --- r4 --- h2
                \\        /
                 -- r3 --

- h1: gera trafego uRLLC (Scapy/TCP) e eMBB (iperf/ffmpeg)
- h2: servidor de destino (rede 5G)
- r1: roteador de entrada -> decide Rota A (via r2) ou Rota B (via r3)
- r2: Rota A (caminho superior)
- r3: Rota B (caminho inferior)
- r4: roteador de saida, precisa manter rota simetrica de volta

Modelo de congestionamento:
- Enlaces de ACESSO (h1<->r1, r4<->h2): 100mbit, banda larga - nao sao gargalo
- Enlaces de TRANSPORTE (r1<->r2<->r4, r1<->r3<->r4): 10mbit, banda limitada -
  e aqui que o trafego eMBB (iperf) vai gerar fila/congestionamento real,
  fazendo a latencia do uRLLC subir organicamente (sem delay artificial).

Uso:
    sudo python3 topologia_diamante.py
"""

from mininet.net import Mininet
from mininet.node import Node
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.topo import Topo


class RoutedTopo(Topo):
    """Topologia diamante: h1 - r1 - (r2 | r3) - r4 - h2"""

    def build(self):
        # Hosts finais
        h1 = self.addHost('h1', ip=None)  # IP configurado manualmente depois
        h2 = self.addHost('h2', ip=None)

        # "Roteadores" -> hosts Linux com IP forwarding
        r1 = self.addHost('r1', ip=None)
        r2 = self.addHost('r2', ip=None)
        r3 = self.addHost('r3', ip=None)
        r4 = self.addHost('r4', ip=None)

        # Enlaces de ACESSO: banda larga, nao sao o gargalo
        self.addLink(h1, r1, cls=TCLink, bw=100)

        # Enlaces de TRANSPORTE (Rota A, via r2): banda limitada de proposito -
        # e aqui que o congestionamento real (eMBB via iperf) vai acontecer
        self.addLink(r1, r2, cls=TCLink, bw=10)
        self.addLink(r2, r4, cls=TCLink, bw=10)

        # Enlaces de TRANSPORTE (Rota B, via r3): mesma capacidade limitada
        self.addLink(r1, r3, cls=TCLink, bw=10)
        self.addLink(r3, r4, cls=TCLink, bw=10)

        # Enlace de ACESSO de saida: banda larga
        self.addLink(r4, h2, cls=TCLink, bw=100)


def config_ips(net):
    """Configura enderecos IP em cada interface manualmente."""

    h1, h2 = net.get('h1', 'h2')
    r1, r2, r3, r4 = net.get('r1', 'r2', 'r3', 'r4')

    # h1 - r1
    h1.setIP('10.0.1.1/30', intf='h1-eth0')
    r1.setIP('10.0.1.2/30', intf='r1-eth0')

    # r1 - r2 (Rota A)
    r1.setIP('10.0.2.1/30', intf='r1-eth1')
    r2.setIP('10.0.2.2/30', intf='r2-eth0')

    # r1 - r3 (Rota B)
    r1.setIP('10.0.3.1/30', intf='r1-eth2')
    r3.setIP('10.0.3.2/30', intf='r3-eth0')

    # r2 - r4
    r2.setIP('10.0.4.1/30', intf='r2-eth1')
    r4.setIP('10.0.4.2/30', intf='r4-eth0')

    # r3 - r4
    r3.setIP('10.0.5.1/30', intf='r3-eth1')
    r4.setIP('10.0.5.2/30', intf='r4-eth1')

    # r4 - h2
    r4.setIP('10.0.6.1/30', intf='r4-eth2')
    h2.setIP('10.0.6.2/30', intf='h2-eth0')


def enable_forwarding(net):
    """Habilita IP forwarding em todos os roteadores."""
    for name in ('r1', 'r2', 'r3', 'r4'):
        r = net.get(name)
        r.cmd('sysctl -w net.ipv4.ip_forward=1')


def config_routes(net, active_route='A'):
    """
    Configura rotas estaticas.

    - h1 e h2 tem rota default apontando para o roteador local (r1/r4)
    - r1 decide, para o destino de h2, se envia via r2 (Rota A) ou r3 (Rota B)
    - r4 precisa ter a rota simetrica de volta para h1 pela MESMA rota,
      senao o TCP quebra (caminho de ida != caminho de volta)
    - r2/r3 so precisam saber como chegar em h2 via r4
    """
    h1, h2 = net.get('h1', 'h2')
    r1, r2, r3, r4 = net.get('r1', 'r2', 'r3', 'r4')

    # Rotas default dos hosts finais
    h1.cmd('ip route add default via 10.0.1.2')
    h2.cmd('ip route add default via 10.0.6.1')

    # r2 e r3 sabem alcancar a rede de h2 (10.0.6.0/30) via r4
    r2.cmd('ip route add 10.0.6.0/30 via 10.0.4.2')
    r3.cmd('ip route add 10.0.6.0/30 via 10.0.5.2')

    # r2 e r3 tambem precisam saber voltar para a rede de h1 (10.0.1.0/30) via r1.
    # Sem isso, o trafego de RETORNO (h2 -> h1) chega em r2/r3 e e descartado
    # por falta de rota, mesmo o caminho de IDA (h1 -> h2) funcionando normalmente.
    r2.cmd('ip route add 10.0.1.0/30 via 10.0.2.1')
    r3.cmd('ip route add 10.0.1.0/30 via 10.0.3.1')

    set_active_route(net, active_route)


def set_active_route(net, route='A'):
    """
    Troca a rota ativa entre R2 (Rota A) e R3 (Rota B).
    Atualiza r1 (ida) e r4 (volta) para manterem simetria.

    Esta e a funcao que o mecanismo de Closed Loop vai chamar
    quando a latencia do fluxo uRLLC ultrapassar 5ms.
    """
    r1, r4 = net.get('r1', 'r4')

    # remove rotas antigas para o destino de h2 / origem de h1, se existirem
    r1.cmd('ip route del 10.0.6.0/30 2>/dev/null')
    r4.cmd('ip route del 10.0.1.0/30 2>/dev/null')

    if route == 'A':
        r1.cmd('ip route add 10.0.6.0/30 via 10.0.2.2')  # via r2
        r4.cmd('ip route add 10.0.1.0/30 via 10.0.4.1')  # volta via r2
        info('*** Rota ativa: A (via r2)\n')
    elif route == 'B':
        r1.cmd('ip route add 10.0.6.0/30 via 10.0.3.2')  # via r3
        r4.cmd('ip route add 10.0.1.0/30 via 10.0.5.1')  # volta via r3
        info('*** Rota ativa: B (via r3)\n')
    else:
        raise ValueError("route deve ser 'A' ou 'B'")


def main():
    setLogLevel('info')

    topo = RoutedTopo()
    net = Mininet(topo=topo, link=TCLink, controller=None)
    net.start()

    config_ips(net)
    enable_forwarding(net)
    config_routes(net, active_route='A')

    info('*** Testando conectividade h1 -> h2\n')
    net.get('h1').cmd('ping -c 2 10.0.6.2')

    info('*** Topologia pronta. Use set_active_route(net, "B") no CLI para trocar de rota.\n')
    CLI(net)

    net.stop()


if __name__ == '__main__':
    main()
