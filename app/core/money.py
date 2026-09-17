"""Módulo central para parsing, conversão e formatação monetária segura.

Regras contábeis fundamentais:
1. Nunca utilizar `float` para cálculos ou armazenamento financeiro.
2. Todas as quantias utilizam `Decimal` com 2 casas decimais e arredondamento ROUND_HALF_UP.
3. Tratamento robusto para formatos monetários brasileiros (ex: '20.000,00', 'R$ 1.234.567,89')
   e formato decimal padrão (ex: '20000.00').
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any

TWO_PLACES = Decimal("0.01")


def parse_brl_money(value: Any) -> Decimal | None:
    """Converte valores em string, número ou Decimal para Decimal(2 casas).
    
    Retorna None se a entrada for None, vazia ou inválida.
    """
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if isinstance(value, int):
        return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    if isinstance(value, float):
        # Converte via string para evitar artefatos binários
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    text = str(value).strip()
    if not text:
        return None

    # Detectar sinal negativo
    is_negative = False
    if text.startswith("-") or "- " in text or " -" in text or text.startswith("("):
        is_negative = True

    # Remover caracteres não numéricos exceto dígitos, vírgula, ponto, menos e mais
    clean = re.sub(r"[^\d.,\-+]", "", text)
    if not clean or clean in ("-", "+", ".", ","):
        return None

    if clean.startswith("+"):
        clean = clean[1:]
    if clean.startswith("-"):
        is_negative = True
        clean = clean[1:]

    # Diferenciar formato brasileiro com vírgula do formato decimal puro
    if "," in clean:
        # Formato BRL: pontos são separadores de milhar e vírgula é o separador decimal
        clean = clean.replace(".", "").replace(",", ".")
    else:
        # Formato sem vírgula: se tiver múltiplos pontos, são separadores de milhar (ex: 1.000.000)
        if clean.count(".") > 1:
            clean = clean.replace(".", "")

    try:
        dec = Decimal(clean).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return -abs(dec) if is_negative else abs(dec)
    except InvalidOperation:
        return None


def format_brl_money(value: Any) -> str:
    """Formata qualquer valor monetário para o padrão monetário brasileiro.
    
    Exemplo: Decimal('20000.00') -> 'R$ 20.000,00'
             Decimal('-2000.00') -> '-R$ 2.000,00'
             None                -> 'R$ 0,00'
    """
    parsed = parse_brl_money(value)
    if parsed is None:
        return "R$ 0,00"

    is_negative = parsed < 0
    abs_d = abs(parsed)
    # Formato inglês: 1,234,567.89
    raw_formatted = f"{abs_d:,.2f}"
    # Inverter separadores para BRL: 1.234.567,89
    brl_formatted = raw_formatted.replace(",", "_").replace(".", ",").replace("_", ".")
    prefix = "-R$ " if is_negative else "R$ "
    return f"{prefix}{brl_formatted}"

