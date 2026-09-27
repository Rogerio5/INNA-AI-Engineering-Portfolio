"""
Extração automática de memória financeira da INNA.

Responsável por identificar, em mensagens do usuário:

- renda mensal;
- gastos mensais;
- capacidade de guardar;
- dívidas;
- uso de cartão;
- metas e objetivos.
"""

from __future__ import annotations

import re
from typing import Any


def normalizar_valor_financeiro(valor_texto: Any):
    """
    Converte textos como:

    R$ 6.300,00
    6300
    6.300
    6300,50

    para float.
    """
    if valor_texto is None:
        return None

    texto = str(valor_texto).lower().strip()

    texto = texto.replace("r$", "")
    texto = texto.replace("reais", "")
    texto = texto.replace("real", "")
    texto = texto.strip()

    if "," in texto:
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".")
    else:
        partes = texto.split(".")

        if len(partes) > 2:
            texto = "".join(partes)

        elif len(partes) == 2:
            parte_decimal = partes[-1]

            if len(parte_decimal) == 3:
                texto = "".join(partes)

    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def _buscar_primeiro_valor(texto: str, padroes: list[str]):
    for padrao in padroes:
        resultado = re.search(
            padrao,
            texto,
            flags=re.IGNORECASE,
        )

        if resultado:
            valor = normalizar_valor_financeiro(
                resultado.group(1)
            )

            if valor is not None:
                return valor

    return None


def extrair_memoria_da_mensagem_inna(mensagem: str) -> dict:
    """
    Extrai informações financeiras da mensagem do usuário.

    Retorno:

    {
        "tem_memoria": bool,
        "dados": dict,
        "resumo": str
    }
    """
    if not mensagem:
        return {
            "tem_memoria": False,
            "dados": {},
            "resumo": "Nenhuma memória financeira detectada.",
        }

    texto = str(mensagem).strip()
    texto_lower = texto.lower()

    dados = {}
    eventos = []

    renda = _buscar_primeiro_valor(
        texto_lower,
        [
            r"(?:agora\s+)?(?:eu\s+)?(?:ganho|recebo)\s*(?:r\$)?\s*([\d\.\,]+)",
            r"(?:minha\s+renda(?:\s+mensal)?\s*(?:é|e|está|esta|de)?)\s*(?:r\$)?\s*([\d\.\,]+)",
            r"(?:salário|salario)\s*(?:é|e|de)?\s*(?:r\$)?\s*([\d\.\,]+)",
        ],
    )

    if renda is not None:
        dados["renda_mensal"] = renda
        eventos.append(
            f"renda mensal atualizada para {renda:.2f}"
        )

    gastos = _buscar_primeiro_valor(
        texto_lower,
        [
            r"(?:meus\s+)?(?:gastos|despesas)\s*(?:mensais\s*)?(?:são|sao|é|e|de)?\s*(?:r\$)?\s*([\d\.\,]+)",
            r"(?:eu\s+)?gasto\s*(?:por\s+m[eê]s\s*)?(?:r\$)?\s*([\d\.\,]+)",
        ],
    )

    if gastos is not None:
        dados["gastos_mensais"] = gastos
        eventos.append(
            f"gastos mensais atualizados para {gastos:.2f}"
        )

    reserva = _buscar_primeiro_valor(
        texto_lower,
        [
            r"(?:consigo|posso|vou|quero)\s+guardar\s*(?:r\$)?\s*([\d\.\,]+)",
            r"(?:eu\s+)?guardo\s*(?:r\$)?\s*([\d\.\,]+)",
            r"(?:capacidade\s+de\s+guardar)\s*(?:é|e|de)?\s*(?:r\$)?\s*([\d\.\,]+)",
        ],
    )

    if reserva is not None:
        dados["valor_reserva"] = reserva
        eventos.append(
            f"capacidade de guardar atualizada para {reserva:.2f}"
        )

    expressoes_com_dividas = [
        "tenho dívida",
        "tenho divida",
        "tenho dívidas",
        "tenho dividas",
        "estou endividado",
        "estou endividada",
    ]

    expressoes_sem_dividas = [
        "não tenho dívida",
        "nao tenho divida",
        "não tenho dívidas",
        "nao tenho dividas",
        "não estou endividado",
        "nao estou endividado",
    ]

    if any(expressao in texto_lower for expressao in expressoes_sem_dividas):
        dados["possui_dividas"] = False
        eventos.append("usuário informou não possuir dívidas")

    elif any(expressao in texto_lower for expressao in expressoes_com_dividas):
        dados["possui_dividas"] = True
        eventos.append("usuário informou possuir dívidas")

    expressoes_cartao = [
        "uso cartão",
        "uso cartao",
        "uso o cartão",
        "uso o cartao",
        "tenho cartão de crédito",
        "tenho cartao de credito",
    ]

    if any(expressao in texto_lower for expressao in expressoes_cartao):
        dados["uso_cartao_credito"] = True
        eventos.append(
            "usuário informou uso de cartão de crédito"
        )

    padrao_meta = re.search(
        r"(?:minha\s+meta\s+(?:é|e)|"
        r"meu\s+objetivo\s+(?:é|e)|"
        r"quero\s+alcançar)\s+(.{5,160})",
        texto,
        flags=re.IGNORECASE,
    )

    if padrao_meta:
        meta = padrao_meta.group(1).strip().rstrip(".")

        dados["ultima_meta"] = meta
        dados["objetivo_principal"] = meta
        eventos.append(
            f"meta ou objetivo atualizado: {meta}"
        )

    if not dados:
        return {
            "tem_memoria": False,
            "dados": {},
            "resumo": "Nenhuma memória financeira detectada.",
        }

    resumo = "; ".join(eventos)

    dados["resumo_contexto"] = resumo
    dados["nivel_confianca"] = 0.85
    dados["tags"] = [
        "memoria_automatica",
        "conversa",
    ]

    return {
        "tem_memoria": True,
        "dados": dados,
        "resumo": resumo,
    }


def mesclar_memoria_existente(
    memoria_atual: dict | None,
    novos_dados: dict | None,
) -> dict:
    """
    Mescla os novos dados com a memória atual sem apagar
    informações que não foram mencionadas na conversa.
    """
    memoria_atual = memoria_atual or {}
    novos_dados = novos_dados or {}

    campos = [
        "nome",
        "idioma",
        "moeda",
        "renda_mensal",
        "gastos_mensais",
        "valor_reserva",
        "possui_dividas",
        "uso_cartao_credito",
        "ultimo_score",
        "ultimo_risco",
        "ultima_meta",
        "resumo_contexto",
        "perfil_financeiro",
        "objetivo_principal",
        "preferencia_linguagem",
        "nivel_confianca",
        "memoria_json",
        "tags",
    ]

    resultado = {}

    for campo in campos:
        if (
            campo in novos_dados
            and novos_dados[campo] is not None
        ):
            resultado[campo] = novos_dados[campo]
        else:
            resultado[campo] = memoria_atual.get(campo)

    resultado["idioma"] = resultado.get("idioma") or "pt"
    resultado["moeda"] = resultado.get("moeda") or "BRL"

    resultado["preferencia_linguagem"] = (
        resultado.get("preferencia_linguagem")
        or "simples"
    )

    resultado["memoria_json"] = (
        resultado.get("memoria_json")
        or {}
    )

    resultado["tags"] = (
        resultado.get("tags")
        or []
    )

    return resultado
