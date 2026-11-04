import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ai_service.modelo import (
    CLASSES, FAIXAS, FEATURES, ModeloRisco, atividade_por_acelerometro, calcular_irp,
    faixa_etaria, normalizar_especie,
)
from ai_service.personalizacao import comparar_com_historico, motivos_da_analise, recomendacao_personalizada
from ai_service.repositorio import criar_repositorio

load_dotenv(Path(__file__).with_name(".env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="PetCare360 IA",
    version="2.0.0",
    description="Serviço de IA do PetCare360 (CLYVO VET): classificação de prioridade com Random Forest, "
                "IRP, personalização por perfil e acompanhamento contínuo por histórico.",
)

modelo = ModeloRisco()
repositorio = criar_repositorio()

COMPORTAMENTOS_ALTERADOS = {"alterado", "anormal", "diferente", "true", "sim"}


class AnaliseEntrada(BaseModel):
    petId: int | None = Field(default=None, ge=1)
    nome: str | None = None
    especie: str | None = None
    raca: str | None = None
    idade: float | None = Field(default=None, ge=0, le=40)
    peso: float | None = Field(default=None, ge=0, le=200)
    temperatura: float = Field(ge=25, le=45)
    umidade: float = Field(default=0, ge=0, le=100)
    atividade: float | None = Field(default=None, ge=0, le=100)
    alimentacao: float = Field(ge=0, le=100)
    comportamento: str = "Normal"
    acelerometro: list[list[float]] | None = None
    origem: str = Field(default="api", max_length=20)


def montar_perfil(d: AnaliseEntrada) -> dict:
    do_banco = repositorio.buscar_pet(d.petId) if d.petId else None
    base = do_banco or {}
    especie = normalizar_especie(base.get("especie") or d.especie)
    idade = base.get("idade") if base.get("idade") is not None else d.idade
    faixa = faixa_etaria(especie, idade)
    return {
        "nome": base.get("nome") or d.nome or "Pet",
        "especie": especie,
        "raca": base.get("raca") or d.raca or "Não informada",
        "idade": idade,
        "peso": base.get("peso") if base.get("peso") is not None else d.peso,
        "faixaEtaria": FAIXAS[faixa],
        "codigoFaixa": faixa,
        "fonte": "banco" if do_banco else "requisicao",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "modelo": "RandomForestClassifier",
        "dataset": "sintetico",
        "persistencia": repositorio.nome,
        "acuracia": modelo.metricas["acuracia"],
    }


@app.get("/api/ia/modelo")
def informacoes_modelo():
    return {
        "algoritmo": "RandomForestClassifier",
        "features": FEATURES,
        "classes": CLASSES,
        "formulaIrp": "IRP = round(10 * (0.5 * P(ATENÇÃO) + 1.0 * P(ALTO)))",
        "metricas": modelo.metricas,
        "observacao": "Métricas calculadas sobre dados sintéticos; não representam validação clínica.",
    }


@app.post("/api/ia/analisar")
def analisar(d: AnaliseEntrada):
    try:
        if d.acelerometro:
            atividade, origem_atividade = atividade_por_acelerometro(d.acelerometro), "acelerometro"
        else:
            atividade, origem_atividade = d.atividade, "informada"
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    if atividade is None:
        raise HTTPException(status_code=422, detail="Informe atividade (0-100) ou amostras XYZ do acelerômetro")

    perfil = montar_perfil(d)
    comportamento_alterado = 1 if d.comportamento.strip().lower() in COMPORTAMENTOS_ALTERADOS else 0

    nivel, probabilidades = modelo.prever(
        d.temperatura, atividade, d.alimentacao, comportamento_alterado, perfil["codigoFaixa"]
    )
    irp = calcular_irp(probabilidades)

    medicamentos = repositorio.medicamentos_ativos(d.petId) if d.petId else None
    historico = repositorio.listar_historico(d.petId, 5) if d.petId else []
    atual = {"temperatura": d.temperatura, "atividade": atividade, "alimentacao": d.alimentacao, "irp": irp}
    tendencia = comparar_com_historico(atual, historico)

    motivos = motivos_da_analise(d.temperatura, atividade, d.alimentacao, comportamento_alterado, perfil["codigoFaixa"])
    motivos += tendencia["alertas"]
    if not motivos:
        motivos.append("Nenhum indicador ultrapassou os limites de referência do protótipo")

    recomendacao = recomendacao_personalizada(
        nivel, perfil["nome"], perfil["especie"], perfil["codigoFaixa"], medicamentos, tendencia
    )

    comportamento = "Alterado" if comportamento_alterado else "Normal"
    id_analise = None
    if d.petId:
        id_analise = repositorio.salvar_analise({
            "petId": d.petId, "origem": d.origem, "temperatura": d.temperatura, "umidade": d.umidade,
            "atividade": atividade, "alimentacao": d.alimentacao, "comportamento": comportamento,
            "nivel": nivel, "irp": irp, "probNormal": probabilidades["NORMAL"],
            "probAtencao": probabilidades["ATENÇÃO"], "probAlto": probabilidades["ALTO"],
        })

    return {
        "idAnalise": id_analise,
        "persistencia": repositorio.nome if id_analise else None,
        "petId": d.petId,
        "nome": perfil["nome"],
        "especie": perfil["especie"],
        "raca": perfil["raca"],
        "idade": perfil["idade"],
        "peso": perfil["peso"],
        "perfil": {k: v for k, v in perfil.items() if k != "codigoFaixa"},
        "telemetria": {
            "temperatura": d.temperatura,
            "umidade": d.umidade,
            "atividade": atividade,
            "origemAtividade": origem_atividade,
            "alimentacao": d.alimentacao,
            "comportamento": comportamento,
        },
        "analiseIA": {
            "nivel": nivel,
            "irp": irp,
            "prioridade": irp,
            "probabilidades": probabilidades,
            "motivos": motivos,
            "recomendacao": recomendacao["texto"],
            "recomendacaoGeral": recomendacao["geral"],
            "recomendacoesPersonalizadas": recomendacao["personalizadas"],
            "medicamentosAtivos": medicamentos,
            "tendencia": tendencia,
        },
        "origem": d.origem,
        "analisadoEm": datetime.now().astimezone().isoformat(timespec="seconds"),
        "observacao": "Apoio à decisão com dados sintéticos; não é diagnóstico veterinário.",
    }


@app.get("/api/ia/pets/{pet_id}/historico")
def historico_pet(pet_id: int, limite: int = Query(default=20, ge=1, le=100)):
    analises = repositorio.listar_historico(pet_id, limite)
    irps = [a["irp"] for a in analises if a.get("irp") is not None]
    return {
        "petId": pet_id,
        "persistencia": repositorio.nome,
        "resumo": {
            "totalAnalises": len(analises),
            "mediaIrp": round(sum(irps) / len(irps), 2) if irps else None,
            "ultimoNivel": analises[-1]["nivel"] if analises else None,
            "ultimoIrp": irps[-1] if irps else None,
            "distribuicaoNiveis": dict(Counter(a["nivel"] for a in analises)),
        },
        "analises": analises,
    }