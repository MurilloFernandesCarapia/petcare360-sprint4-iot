"""PetCare360 AI proof of concept: Random Forest + IRP.
This prototype is for software demonstration only, not veterinary diagnosis.
"""
from __future__ import annotations
import os
from datetime import date, datetime
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

app = FastAPI(title="PetCare360 AI", version="1.0.0", description="Prototype for triage support; not a veterinary diagnostic tool")

FEATURES = ["temperatura", "atividade", "alimentacao", "comportamento_alterado"]
CLASSES = ["NORMAL", "ATENÇÃO", "ALTO"]

class AnaliseEntrada(BaseModel):
    petId: int | None = None
    nome: str = "Pet"
    especie: str = "Não informada"
    raca: str = "Não informada"
    idade: float = Field(default=0, ge=0, le=40)
    peso: float = Field(default=0, ge=0, le=200)
    temperatura: float = Field(ge=25, le=45)
    umidade: float = Field(default=0, ge=0, le=100)
    atividade: float | None = Field(default=None, ge=0, le=100)
    alimentacao: float = Field(ge=0, le=100)
    comportamento: str = "Normal"
    acelerometro: list[list[float]] | None = None
    historico: dict[str, Any] = Field(default_factory=dict)


def activity_from_accelerometer(samples: list[list[float]]) -> float:
    """Convert XYZ acceleration samples into a demonstrative 0-100 activity index.

    Uses the standard deviation of the deviation from 1 g, then maps a calibrated
    range [0.02, 0.60] g to [0, 100]. Sensor sampling/calibration must be validated
    for the actual device before production use.
    """
    arr = np.asarray(samples, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 3 or len(arr) < 3:
        raise ValueError("acelerometro precisa conter pelo menos 3 amostras [x,y,z]")
    if not np.isfinite(arr).all():
        raise ValueError("amostras do acelerômetro devem ser numéricas")
    magnitude = np.sqrt(np.sum(arr ** 2, axis=1))
    dynamic = float(np.std(magnitude - 1.0))
    return round(float(np.clip((dynamic - 0.02) / (0.60 - 0.02) * 100, 0, 100)), 2)


def synthetic_training_data(n: int = 2400, seed: int = 42):
    """Create reproducible synthetic demonstration data, not clinical evidence."""
    rng = np.random.default_rng(seed)
    temp = rng.uniform(37.0, 41.0, n)
    activity = rng.uniform(0, 100, n)
    food = rng.uniform(0, 100, n)
    behavior = rng.integers(0, 2, n)
    # Synthetic labels imitate transparent triage patterns solely to make a runnable demo.
    score = np.zeros(n)
    score += np.where(temp >= 39.5, 4, np.where(temp >= 39.0, 2, 0))
    score += np.where(activity < 30, 3, np.where(activity < 50, 1, 0))
    score += np.where(food < 40, 3, np.where(food < 60, 1, 0))
    score += behavior
    labels = np.where(score >= 7, "ALTO", np.where(score >= 4, "ATENÇÃO", "NORMAL"))
    X = np.column_stack([temp, activity, food, behavior])
    return X, labels

X, y = synthetic_training_data()
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
model = RandomForestClassifier(n_estimators=160, max_depth=10, min_samples_leaf=3, random_state=42, class_weight="balanced")
model.fit(X_train, y_train)
DEMO_ACCURACY = round(float(accuracy_score(y_test, model.predict(X_test))), 4)


def active_medication_from_oracle(pet_id: int | None) -> bool | None:
    """Read current medication from TB_MEDICAMENTO when Oracle is configured.

    Returns None when DB configuration/driver is absent; it never trusts medication
    status sent as continuous telemetry. Set ORACLE_USER, ORACLE_PASSWORD and
    ORACLE_DSN (e.g. host:1521/service) and install oracledb to enable the query.
    """
    if not pet_id or not all(os.getenv(k) for k in ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN")):
        return None
    try:
        import oracledb
        with oracledb.connect(user=os.environ["ORACLE_USER"], password=os.environ["ORACLE_PASSWORD"], dsn=os.environ["ORACLE_DSN"]) as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END
                               FROM TB_MEDICAMENTO
                              WHERE ID_PET = :pet_id
                                AND DT_INICIO <= TRUNC(SYSDATE)
                                AND (DT_FIM IS NULL OR DT_FIM >= TRUNC(SYSDATE))""", pet_id=pet_id)
                return bool(cur.fetchone()[0])
    except Exception:
        # Do not expose database credentials/errors in the API response.
        return None


def compute_irp(probabilities: dict[str, float]) -> int:
    """IRP = round(10 * (P(ATENÇÃO)*0.5 + P(ALTO)*1.0)), clipped to 0..10."""
    raw = 10 * (0.5 * probabilities.get("ATENÇÃO", 0.0) + probabilities.get("ALTO", 0.0))
    return int(np.clip(np.rint(raw), 0, 10))

@app.get("/health")
def health():
    return {"status": "ok", "model": "RandomForestClassifier", "dataset": "synthetic_demo", "demo_accuracy": DEMO_ACCURACY}

@app.post("/api/ia/analisar")
def analisar(d: AnaliseEntrada):
    try:
        activity = activity_from_accelerometer(d.acelerometro) if d.acelerometro else d.atividade
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if activity is None:
        raise HTTPException(status_code=422, detail="Informe atividade (0-100) ou amostras XYZ do acelerômetro")
    behavior = 1 if d.comportamento.strip().lower() in {"alterado", "anormal", "diferente"} else 0
    vector = np.array([[d.temperatura, activity, d.alimentacao, behavior]], dtype=float)
    pred = str(model.predict(vector)[0])
    probs_arr = model.predict_proba(vector)[0]
    probs = {str(label): float(prob) for label, prob in zip(model.classes_, probs_arr)}
    irp = compute_irp(probs)
    # medication is a historical clinical datum; it is retrieved from Oracle, not telemetry.
    med = active_medication_from_oracle(d.petId)
    motivos = []
    if d.temperatura >= 39.0: motivos.append("Temperatura elevada em relação aos limites de referência usados no protótipo")
    if activity < 50: motivos.append("Índice de atividade reduzido")
    if d.alimentacao < 60: motivos.append("Índice de alimentação reduzido")
    if behavior: motivos.append("Comportamento informado como alterado")
    if med is True: motivos.append("Há medicamento ativo registrado no banco de dados; contexto a ser considerado pela clínica")
    if not motivos: motivos.append("Nenhum dos sinais de entrada ultrapassou os limiares descritivos do protótipo")
    recommendation = {
        "NORMAL": "Manter a rotina de acompanhamento e registrar novas observações.",
        "ATENÇÃO": "Rever os indicadores e considerar contato com a clínica se a alteração persistir.",
        "ALTO": "Priorizar contato com um médico-veterinário; não aguardar apenas pelo sistema se houver sinais graves."
    }[pred]
    return {
        "petId": d.petId, "nome": d.nome, "especie": d.especie, "raca": d.raca,
        "idade": d.idade, "peso": d.peso,
        "telemetria": {"temperatura": d.temperatura, "umidade": d.umidade, "atividade": activity,
                       "alimentacao": d.alimentacao, "comportamento": d.comportamento},
        "analiseIA": {"nivel": pred, "prioridade": irp, "irp": irp, "probabilidades": {k: round(v, 4) for k, v in probs.items()},
                       "recomendacao": recommendation, "motivos": motivos, "medicamentoAtivoNoBanco": med},
        "analisadoEm": datetime.now().astimezone().isoformat(),
        "observacao": "Protótipo experimental com dados sintéticos; não é diagnóstico nem modelo clinicamente validado.",
        "metadadosModelo": {"algoritmo": "RandomForestClassifier", "dataset": "sintético para demonstração", "acuraciaTesteDemonstrativa": DEMO_ACCURACY}
    }
