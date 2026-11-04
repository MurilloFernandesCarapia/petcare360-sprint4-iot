from statistics import mean

from ai_service.modelo import FAIXAS

RECOMENDACOES = {
    "NORMAL": "Manter a rotina de acompanhamento e registrar novas observações.",
    "ATENÇÃO": "Rever os indicadores nas próximas horas e contatar a clínica se a alteração persistir.",
    "ALTO": "Priorizar contato com um médico-veterinário; não aguardar apenas pelo sistema se houver sinais graves.",
}

JANELA_HISTORICO = 5


def motivos_da_analise(temperatura: float, atividade: float, alimentacao: float,
                       comportamento_alterado: int, faixa: int) -> list[str]:
    motivos = []
    if temperatura >= 39.5:
        motivos.append("Temperatura bem acima da faixa de referência usada no protótipo")
    elif temperatura >= 39.0:
        motivos.append("Temperatura levemente elevada")
    if atividade < 30:
        motivos.append("Atividade muito reduzida")
    elif atividade < 50:
        motivos.append("Atividade abaixo do esperado")
    if alimentacao < 40:
        motivos.append("Alimentação muito reduzida")
    elif alimentacao < 60:
        motivos.append("Alimentação abaixo do esperado")
    if comportamento_alterado:
        motivos.append("Comportamento informado como alterado")
    if faixa != 1:
        motivos.append(f"Pet na faixa etária '{FAIXAS[faixa]}', considerada mais sensível pelo modelo")
    return motivos


def _media(registros: list[dict], campo: str) -> float | None:
    valores = [r[campo] for r in registros if r.get(campo) is not None]
    return mean(valores) if valores else None


def comparar_com_historico(atual: dict, historico: list[dict]) -> dict:
    recentes = historico[-JANELA_HISTORICO:]
    if not recentes:
        return {
            "status": "SEM_HISTORICO",
            "descricao": "Primeira análise registrada para este pet; as próximas serão comparadas com ela.",
            "analisesConsideradas": 0,
            "variacoes": {},
            "alertas": [],
        }

    variacoes = {}
    for campo in ("temperatura", "atividade", "alimentacao", "irp"):
        media = _media(recentes, campo)
        if media is not None and atual.get(campo) is not None:
            variacoes[campo] = round(atual[campo] - media, 2)

    alertas = []
    if variacoes.get("temperatura", 0) >= 0.5:
        alertas.append(f"Temperatura {variacoes['temperatura']:.1f} °C acima da média recente do próprio pet")
    if variacoes.get("atividade", 0) <= -20:
        alertas.append(f"Atividade {abs(variacoes['atividade']):.0f} pontos abaixo da média recente do próprio pet")
    if variacoes.get("alimentacao", 0) <= -20:
        alertas.append(f"Alimentação {abs(variacoes['alimentacao']):.0f} pontos abaixo da média recente do próprio pet")

    variacao_irp = variacoes.get("irp", 0)
    if variacao_irp >= 2:
        status, descricao = "PIORA", "O IRP subiu em relação às últimas análises do pet."
    elif variacao_irp <= -2:
        status, descricao = "MELHORA", "O IRP caiu em relação às últimas análises do pet."
    else:
        status, descricao = "ESTAVEL", "Os indicadores estão parecidos com as últimas análises do pet."

    return {
        "status": status,
        "descricao": descricao,
        "analisesConsideradas": len(recentes),
        "variacoes": variacoes,
        "alertas": alertas,
    }


def recomendacao_personalizada(nivel: str, nome: str, especie: str, faixa: int,
                               medicamentos: list[str] | None, tendencia: dict) -> dict:
    dicas = []
    if faixa == 2:
        dicas.append(f"{nome} está na faixa idosa para a espécie ({especie}): comunique à clínica mudanças de apetite ou disposição mais cedo do que faria com um pet adulto.")
    elif faixa == 0:
        dicas.append(f"{nome} é filhote: queda de alimentação merece contato rápido com a clínica.")
    if medicamentos:
        dicas.append(f"Há medicamento em uso registrado ({', '.join(medicamentos)}): informe a clínica sobre as alterações observadas.")
    if tendencia["status"] == "PIORA":
        dicas.append("Os indicadores pioraram em relação ao histórico do próprio pet; acompanhe mais de perto nos próximos dias.")
    elif tendencia["status"] == "MELHORA" and nivel != "ALTO":
        dicas.append("Os indicadores melhoraram em relação às últimas análises; mantenha a rotina de registros.")

    return {
        "geral": RECOMENDACOES[nivel],
        "personalizadas": dicas,
        "texto": " ".join([RECOMENDACOES[nivel], *dicas]),
    }