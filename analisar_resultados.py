#!/usr/bin/env python3
"""
Analisa e compara os dois cenarios do experimento (SEM QoS x COM QoS).

Le os arquivos gerados por rodar_experimento.py (renomeados apos cada
execucao) e produz:
  1. Um resumo estatistico no terminal (latencia media antes/durante o
     eMBB, pico maximo, % de amostras acima do limiar de 5ms)
  2. Um grafico comparativo (latencia_comparacao.png) mostrando a
     latencia ao longo do tempo nos dois cenarios, com a janela do
     eMBB destacada e a linha do limiar de 5ms.

Uso:
    python3 analisar_resultados.py
"""

import csv
import json

import matplotlib.pyplot as plt

LIMIAR_MS = 5.0

CENARIOS = [
    {'nome': 'SEM QoS', 'csv': 'resultado_sem_qos.csv', 'json': 'eventos_sem_qos.json'},
    {'nome': 'COM QoS', 'csv': 'resultado_com_qos.csv', 'json': 'eventos_com_qos.json'},
]


def carregar_dados(caminho_csv):
    tempos, valores = [], []
    with open(caminho_csv) as f:
        for linha in csv.DictReader(f):
            if linha['owd_ms'] == '':
                continue
            tempos.append(float(linha['timestamp_chegada']))
            valores.append(float(linha['owd_ms']))
    return tempos, valores


def analisar(cenario):
    tempos, valores = carregar_dados(cenario['csv'])
    with open(cenario['json']) as f:
        eventos = json.load(f)

    t0 = tempos[0]
    tempos_rel = [t - t0 for t in tempos]
    inicio_rel = eventos['inicio_embb'] - t0
    fim_rel = eventos['fim_embb'] - t0

    antes = [v for t, v in zip(tempos_rel, valores) if t < inicio_rel]
    durante = [v for t, v in zip(tempos_rel, valores) if inicio_rel <= t <= fim_rel]
    depois = [v for t, v in zip(tempos_rel, valores) if t > fim_rel]

    def media(lista):
        return sum(lista) / len(lista) if lista else float('nan')

    def pct_acima_limiar(lista):
        if not lista:
            return float('nan')
        return 100 * sum(1 for v in lista if v > LIMIAR_MS) / len(lista)

    print(f"\n=== {cenario['nome']} ===")
    print(f"Amostras totais: {len(valores)}")
    print(f"Latencia media ANTES do eMBB:   {media(antes):.2f} ms  "
          f"({pct_acima_limiar(antes):.1f}% acima de {LIMIAR_MS}ms)")
    print(f"Latencia media DURANTE o eMBB:  {media(durante):.2f} ms  "
          f"({pct_acima_limiar(durante):.1f}% acima de {LIMIAR_MS}ms)")
    print(f"Latencia media DEPOIS do eMBB:  {media(depois):.2f} ms  "
          f"({pct_acima_limiar(depois):.1f}% acima de {LIMIAR_MS}ms)")
    print(f"Pico maximo de latencia:        {max(valores):.2f} ms")

    return tempos_rel, valores, inicio_rel, fim_rel


def gerar_grafico(resultados):
    fig, eixos = plt.subplots(len(resultados), 1, figsize=(10, 8), sharex=False)
    if len(resultados) == 1:
        eixos = [eixos]

    for eixo, (cenario, (tempos_rel, valores, inicio_rel, fim_rel)) in zip(eixos, resultados):
        eixo.plot(tempos_rel, valores, marker='.', linewidth=0.8, markersize=3, label='OWD medido')
        eixo.axvspan(inicio_rel, fim_rel, color='orange', alpha=0.2, label='Trafego eMBB ativo')
        eixo.axhline(LIMIAR_MS, color='red', linestyle='--', linewidth=1, label=f'Limiar {LIMIAR_MS}ms')
        eixo.set_title(cenario['nome'])
        eixo.set_ylabel('OWD (ms)')
        eixo.legend(loc='upper right', fontsize=8)
        eixo.grid(True, alpha=0.3)

    eixos[-1].set_xlabel('Tempo (s)')
    plt.tight_layout()
    plt.savefig('latencia_comparacao.png', dpi=150)
    print("\nGrafico salvo em: latencia_comparacao.png")


def main():
    resultados = []
    for cenario in CENARIOS:
        dados = analisar(cenario)
        resultados.append((cenario, dados))
    gerar_grafico(resultados)


if __name__ == '__main__':
    main()
