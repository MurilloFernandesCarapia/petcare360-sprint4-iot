import unicodedata

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import cross_val_score, train_test_split

FEATURES = ["temperatura", "atividade", "alimentacao", "comportamento_alterado", "faixa_etaria"]
CLASSES = ["NORMAL", "ATENÇÃO", "ALTO"]
FAIXAS = {0: "filhote", 1: "adulto", 2: "idoso"}

ESPECIES = {
    "cao": "Cão",
    "cachorro": "Cão",
    "canino": "Cão",
    "dog": "Cão",
    "gato": "Gato",
    "felino": "Gato",
    "cat": "Gato",
}

PARAMETROS_RF = {
    "n_estimators": 200,
    "max_depth": 10,
    "min_samples_leaf": 3,
    "class_weight": "balanced",
    "random_state": 42,
    "n_jobs": -1,
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def normalizar_especie(especie: str | None) -> str:
    chave = _sem_acento((especie or "").strip().lower())
    return ESPECIES.get(chave, (especie or "Não informada").strip() or "Não informada")


def faixa_etaria(especie: str, idade: float | None) -> int:
    if idade is None:
        return 1
    if idade < 1:
        return 0
    limite_idoso = 10 if especie == "Gato" else 7
    return 2 if idade >= limite_idoso else 1


def atividade_por_acelerometro(amostras: list[list[float]]) -> float:
    dados = np.asarray(amostras, dtype=float)
    if dados.ndim != 2 or dados.shape[1] != 3 or len(dados) < 3:
        raise ValueError("acelerometro precisa conter pelo menos 3 amostras [x,y,z]")
    if not np.isfinite(dados).all():
        raise ValueError("amostras do acelerômetro devem ser numéricas")
    magnitude = np.sqrt(np.sum(dados ** 2, axis=1))
    dinamica = float(np.std(magnitude - 1.0))
    return round(float(np.clip((dinamica - 0.02) / (0.60 - 0.02) * 100, 0, 100)), 2)


def calcular_irp(probabilidades: dict[str, float]) -> int:
    bruto = 10 * (0.5 * probabilidades.get("ATENÇÃO", 0.0) + probabilidades.get("ALTO", 0.0))
    return int(np.clip(np.rint(bruto), 0, 10))


def gerar_dados_sinteticos(n: int = 3000, seed: int = 42):
    rng = np.random.default_rng(seed)
    temperatura = rng.uniform(37.0, 41.0, n)
    atividade = rng.uniform(0, 100, n)
    alimentacao = rng.uniform(0, 100, n)
    comportamento = rng.integers(0, 2, n)
    faixa = rng.choice([0, 1, 2], size=n, p=[0.2, 0.5, 0.3])

    pontos = np.zeros(n)
    pontos += np.where(temperatura >= 39.5, 4, np.where(temperatura >= 39.0, 2, 0))
    pontos += np.where(atividade < 30, 3, np.where(atividade < 50, 1, 0))
    pontos += np.where(alimentacao < 40, 3, np.where(alimentacao < 60, 1, 0))
    pontos += comportamento
    pontos += np.where(faixa != 1, 1, 0)
    rotulos = np.where(pontos >= 7, "ALTO", np.where(pontos >= 4, "ATENÇÃO", "NORMAL"))

    medidas = np.column_stack([
        temperatura + rng.normal(0, 0.15, n),
        np.clip(atividade + rng.normal(0, 5, n), 0, 100),
        np.clip(alimentacao + rng.normal(0, 5, n), 0, 100),
        comportamento,
        faixa,
    ])
    return medidas, rotulos


class ModeloRisco:
    def __init__(self, seed: int = 42):
        X, y = gerar_dados_sinteticos(seed=seed)
        X_treino, X_teste, y_treino, y_teste = train_test_split(
            X, y, test_size=0.2, random_state=seed, stratify=y
        )
        self.rf = RandomForestClassifier(**PARAMETROS_RF)
        self.rf.fit(X_treino, y_treino)

        previsto = self.rf.predict(X_teste)
        validacao = cross_val_score(RandomForestClassifier(**PARAMETROS_RF), X, y, cv=5)
        relatorio = classification_report(y_teste, previsto, output_dict=True, zero_division=0)

        self.metricas = {
            "amostrasTreino": int(len(X_treino)),
            "amostrasTeste": int(len(X_teste)),
            "acuracia": round(float(accuracy_score(y_teste, previsto)), 4),
            "validacaoCruzada5Folds": {
                "media": round(float(validacao.mean()), 4),
                "desvioPadrao": round(float(validacao.std()), 4),
            },
            "porClasse": {
                classe: {
                    "precisao": round(relatorio[classe]["precision"], 4),
                    "recall": round(relatorio[classe]["recall"], 4),
                    "f1": round(relatorio[classe]["f1-score"], 4),
                }
                for classe in CLASSES
            },
            "matrizConfusao": {
                "ordem": CLASSES,
                "valores": confusion_matrix(y_teste, previsto, labels=CLASSES).tolist(),
            },
            "importanciaFeatures": {
                nome: round(float(valor), 4) for nome, valor in zip(FEATURES, self.rf.feature_importances_)
            },
        }

    def prever(self, temperatura: float, atividade: float, alimentacao: float,
               comportamento_alterado: int, faixa: int) -> tuple[str, dict[str, float]]:
        vetor = np.array([[temperatura, atividade, alimentacao, comportamento_alterado, faixa]], dtype=float)
        nivel = str(self.rf.predict(vetor)[0])
        brutas = dict(zip(self.rf.classes_, self.rf.predict_proba(vetor)[0]))
        probabilidades = {classe: round(float(brutas.get(classe, 0.0)), 4) for classe in CLASSES}
        return nivel, probabilidades