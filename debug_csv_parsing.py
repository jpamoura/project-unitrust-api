#!/usr/bin/env python3
"""
Script para debugar o parsing de CSV e identificar o problema de mapeamento de colunas.
"""

import csv
import re
from io import StringIO

def normalize_csv_content(content: str) -> str:
    """
    Normaliza o conteúdo CSV para lidar com diferentes formatos de aspas.
    Converte aspas duplas escapadas (""texto"") para aspas simples normais ("texto").
    """
    # Remove aspas duplas escapadas e substitui por aspas simples normais
    # Padrão: ""texto"" -> "texto"
    normalized = re.sub(r'""([^"]*?)""', r'"\1"', content)
    
    return normalized

def test_csv_parsing():
    """
    Testa diferentes formas de parsing CSV para identificar o problema.
    """
    
    # Exemplo baseado no que o usuário mostrou - dados que estão sendo mapeados incorretamente
    sample_csv = '''WritingAgent,AgentName,Company,Policy,Status,DOB,PolicyDate,PaidtoDate,RecvDate,LastName,FirstName,MI,Plan,Face,Form,Mode,ModePrem,Address1,Address2,Address3,Address4,State,Zip,Phone,Email,"App Date",WrtPct
0001100391,BREWER/ ZACH",110,0108338110,0108338110,07/22/1944,10/10/2024,10/10/2024,10/10/2024,BLISS,JEAN,M,DSI5N,4500,Bank Draft,monthly,52.61,ADDRESS UNKNOWN ****11-07-2024****,502 RAMPEY ST,EASLEY SC 29640,,,SC,29640,864-810-3727,,10/08/2024,100"'''
    
    print("=== TESTE DE PARSING CSV ===\n")
    
    # Teste 1: Parsing padrão
    print("1. PARSING PADRÃO:")
    try:
        reader = csv.DictReader(StringIO(sample_csv))
        rows = list(reader)
        if rows:
            print("Colunas encontradas:", list(rows[0].keys()))
            print("Primeira linha:")
            for key, value in rows[0].items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"Erro: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Teste 2: Com normalização
    print("2. COM NORMALIZAÇÃO:")
    try:
        normalized = normalize_csv_content(sample_csv)
        reader = csv.DictReader(StringIO(normalized))
        rows = list(reader)
        if rows:
            print("Colunas encontradas:", list(rows[0].keys()))
            print("Primeira linha:")
            for key, value in rows[0].items():
                print(f"  {key}: {value}")
    except Exception as e:
        print(f"Erro: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Teste 3: Diferentes configurações
    print("3. DIFERENTES CONFIGURAÇÕES:")
    configs = [
        {'quoting': csv.QUOTE_ALL, 'skipinitialspace': True},
        {'quoting': csv.QUOTE_MINIMAL, 'skipinitialspace': True},
        {'quoting': csv.QUOTE_NONE, 'skipinitialspace': True},
        {'quoting': csv.QUOTE_ALL, 'skipinitialspace': True, 'escapechar': '\\'},
        {'quoting': csv.QUOTE_MINIMAL, 'skipinitialspace': True, 'escapechar': '\\'},
    ]
    
    for i, config in enumerate(configs, 1):
        print(f"3.{i} Configuração {config}:")
        try:
            reader = csv.DictReader(StringIO(sample_csv), **config)
            rows = list(reader)
            if rows:
                print("  Colunas:", list(rows[0].keys()))
                print("  Primeira linha:")
                for key, value in rows[0].items():
                    print(f"    {key}: {value}")
        except Exception as e:
            print(f"  Erro: {e}")
        print()

if __name__ == "__main__":
    test_csv_parsing()
