"""Normalizador de nomes de credores e extrator de CPF/CNPJ."""

import re
import unicodedata


def clean_digits(val: str | None) -> str:
    if not val:
        return ""
    return re.sub(r"\D", "", val)


def validate_cpf(cpf: str) -> bool:
    digits = clean_digits(cpf)
    if len(digits) != 11:
        return False
    if digits == digits[0] * 11:
        return False
    # Primeiro dígito verificador
    s = sum(int(digits[i]) * (10 - i) for i in range(9))
    d1 = 11 - (s % 11)
    d1 = 0 if d1 >= 10 else d1
    if int(digits[9]) != d1:
        return False
    # Segundo dígito verificador
    s = sum(int(digits[i]) * (11 - i) for i in range(10))
    d2 = 11 - (s % 11)
    d2 = 0 if d2 >= 10 else d2
    return int(digits[10]) == d2


def validate_cnpj(cnpj: str) -> bool:
    digits = clean_digits(cnpj)
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False
    # Primeiro dígito
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s1 = sum(int(digits[i]) * w1[i] for i in range(12))
    d1 = 11 - (s1 % 11)
    d1 = 0 if d1 >= 10 else d1
    if int(digits[12]) != d1:
        return False
    # Segundo dígito
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s2 = sum(int(digits[i]) * w2[i] for i in range(13))
    d2 = 11 - (s2 % 11)
    d2 = 0 if d2 >= 10 else d2
    return int(digits[13]) == d2


def format_cpf(digits: str) -> str:
    d = clean_digits(digits)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def format_cnpj(digits: str) -> str:
    d = clean_digits(digits)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def normalize_supplier_name(raw_name: str | None) -> str:
    if not raw_name:
        return ""
    # Remover acentos e converter para maiúsculas
    norm = unicodedata.normalize("NFKD", raw_name)
    without_accents = "".join(c for c in norm if not unicodedata.combining(c)).upper()
    # Limpar pontuações isoladas de início/fim e múltiplos espaços
    cleaned = re.sub(r"\s+", " ", without_accents).strip()
    return cleaned


def extract_document_and_name(raw_favored: str | None) -> dict[str, str | None]:
    """Extrai documento (CPF/CNPJ) e normaliza o nome do favorecido.
    
    Exemplos:
    - '63.162.977 PAULO JOAQUIM DA SILVA JUNIOR' -> document=None (8 dígitos não é CNPJ completo)
    - '01.234.567/0001-89 EMPRESA ABC' -> document='01.234.567/0001-89', doc_type='CNPJ'
    - '123.456.789-00 JOAO DA SILVA' -> document='123.456.789-00', doc_type='CPF'
    """
    if not raw_favored:
        return {
            "document": None,
            "document_type": None,
            "normalized_name": "",
        }

    text = raw_favored.strip()

    # 1. Tentar capturar CNPJ formatado ou 14 dígitos contíguos
    cnpj_match = re.search(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", text)
    if cnpj_match:
        doc_str = cnpj_match.group(0)
        digits = clean_digits(doc_str)
        if len(digits) == 14:
            name_part = text.replace(doc_str, "").strip(" -:/")
            return {
                "document": format_cnpj(digits),
                "document_type": "CNPJ",
                "normalized_name": normalize_supplier_name(name_part) or normalize_supplier_name(text),
            }

    # 2. Tentar capturar CPF formatado ou 11 dígitos contíguos
    cpf_match = re.search(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", text)
    if cpf_match:
        doc_str = cpf_match.group(0)
        digits = clean_digits(doc_str)
        if len(digits) == 11:
            name_part = text.replace(doc_str, "").strip(" -:/")
            return {
                "document": format_cpf(digits),
                "document_type": "CPF",
                "normalized_name": normalize_supplier_name(name_part) or normalize_supplier_name(text),
            }

    # 3. Nenhum documento válido de 11 ou 14 dígitos encontrado
    return {
        "document": None,
        "document_type": None,
        "normalized_name": normalize_supplier_name(text),
    }

