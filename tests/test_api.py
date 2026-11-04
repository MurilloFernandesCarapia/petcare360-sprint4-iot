import os
import tempfile
import unittest
from pathlib import Path

PASTA_TESTE = tempfile.mkdtemp()
os.environ["PETCARE360_SQLITE"] = str(Path(PASTA_TESTE) / "teste.db")
for variavel in ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN"):
    os.environ[variavel] = ""

from fastapi.testclient import TestClient

from ai_service.main import app

PERFIL = {"nome": "Thor", "especie": "Cachorro", "raca": "Golden Retriever", "idade": 4, "peso": 30.5}

CENARIOS = {
    "NORMAL": {"temperatura": 38.3, "umidade": 55, "atividade": 78, "alimentacao": 90, "comportamento": "Normal"},
    "ATENÇÃO": {"temperatura": 39.3, "umidade": 68, "atividade": 40, "alimentacao": 50, "comportamento": "Alterado"},
    "ALTO": {"temperatura": 39.8, "umidade": 72, "atividade": 20, "alimentacao": 35, "comportamento": "Alterado"},
}


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cliente = TestClient(app)

    def analisar(self, **dados):
        return self.cliente.post("/api/ia/analisar", json=dados)

    def test_health(self):
        resposta = self.cliente.get("/health").json()
        self.assertEqual(resposta["status"], "ok")
        self.assertEqual(resposta["persistencia"], "sqlite")

    def test_endpoint_do_modelo(self):
        resposta = self.cliente.get("/api/ia/modelo").json()
        importancias = resposta["metricas"]["importanciaFeatures"]
        self.assertAlmostEqual(sum(importancias.values()), 1.0, places=2)
        self.assertEqual(len(resposta["metricas"]["matrizConfusao"]["valores"]), 3)

    def test_tres_cenarios_de_uso(self):
        for nivel_esperado, cenario in CENARIOS.items():
            with self.subTest(cenario=nivel_esperado):
                resposta = self.analisar(**PERFIL, **cenario)
                self.assertEqual(resposta.status_code, 200)
                analise = resposta.json()["analiseIA"]
                self.assertEqual(analise["nivel"], nivel_esperado)
                self.assertTrue(0 <= analise["irp"] <= 10)

    def test_irp_cresce_com_a_gravidade(self):
        irps = [self.analisar(**PERFIL, **c).json()["analiseIA"]["irp"] for c in CENARIOS.values()]
        self.assertEqual(irps, sorted(irps))

    def test_atividade_calculada_pelo_acelerometro(self):
        amostras = [[0, 0, 1 + (0.6 if i % 2 else -0.6)] for i in range(30)]
        resposta = self.analisar(temperatura=38.3, alimentacao=90, acelerometro=amostras).json()
        self.assertEqual(resposta["telemetria"]["origemAtividade"], "acelerometro")
        self.assertGreater(resposta["telemetria"]["atividade"], 90)

    def test_valida_entrada_sem_atividade(self):
        self.assertEqual(self.analisar(temperatura=38.0, alimentacao=50).status_code, 422)

    def test_valida_temperatura_fora_da_faixa(self):
        self.assertEqual(self.analisar(temperatura=60, alimentacao=50, atividade=50).status_code, 422)

    def test_personaliza_para_pet_idoso(self):
        resposta = self.analisar(**{**PERFIL, "idade": 9}, **CENARIOS["ATENÇÃO"]).json()
        self.assertEqual(resposta["perfil"]["faixaEtaria"], "idoso")
        self.assertTrue(any("idosa" in dica for dica in resposta["analiseIA"]["recomendacoesPersonalizadas"]))

    def test_persiste_e_acompanha_historico(self):
        pet = {"petId": 77, **PERFIL}
        for _ in range(3):
            primeira = self.analisar(**pet, **CENARIOS["NORMAL"]).json()
            self.assertIsNotNone(primeira["idAnalise"])
        piora = self.analisar(**pet, **CENARIOS["ALTO"]).json()
        self.assertEqual(piora["analiseIA"]["tendencia"]["status"], "PIORA")

        historico = self.cliente.get("/api/ia/pets/77/historico").json()
        self.assertEqual(historico["resumo"]["totalAnalises"], 4)
        self.assertEqual(historico["resumo"]["ultimoNivel"], "ALTO")
        self.assertEqual([a["nivel"] for a in historico["analises"]], ["NORMAL", "NORMAL", "NORMAL", "ALTO"])


if __name__ == "__main__":
    unittest.main()