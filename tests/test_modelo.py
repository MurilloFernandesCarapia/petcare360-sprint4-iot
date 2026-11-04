import unittest

from ai_service.modelo import (
    ModeloRisco, atividade_por_acelerometro, calcular_irp, faixa_etaria, normalizar_especie,
)
from ai_service.personalizacao import comparar_com_historico


class TestIrp(unittest.TestCase):
    def test_formula_nos_extremos(self):
        self.assertEqual(calcular_irp({"NORMAL": 1.0}), 0)
        self.assertEqual(calcular_irp({"ATENÇÃO": 1.0}), 5)
        self.assertEqual(calcular_irp({"ALTO": 1.0}), 10)

    def test_formula_com_probabilidades_mistas(self):
        self.assertEqual(calcular_irp({"NORMAL": 0.2, "ATENÇÃO": 0.4, "ALTO": 0.4}), 6)


class TestAcelerometro(unittest.TestCase):
    def test_pet_parado_tem_atividade_baixa(self):
        parado = [[0, 0, 1], [0.01, 0, 1], [0, 0.01, 1], [0, 0, 1.01]]
        self.assertLess(atividade_por_acelerometro(parado), 10)

    def test_pet_agitado_tem_atividade_alta(self):
        agitado = [[0, 0, 1 + (0.8 if i % 2 else -0.8)] for i in range(20)]
        self.assertGreater(atividade_por_acelerometro(agitado), 90)

    def test_rejeita_poucas_amostras(self):
        with self.assertRaises(ValueError):
            atividade_por_acelerometro([[0, 0, 1], [0, 0, 1]])


class TestPerfil(unittest.TestCase):
    def test_normaliza_especie(self):
        self.assertEqual(normalizar_especie("cachorro"), "Cão")
        self.assertEqual(normalizar_especie("Cão"), "Cão")
        self.assertEqual(normalizar_especie("FELINO"), "Gato")

    def test_faixa_etaria_por_especie(self):
        self.assertEqual(faixa_etaria("Cão", 0.5), 0)
        self.assertEqual(faixa_etaria("Cão", 8), 2)
        self.assertEqual(faixa_etaria("Gato", 8), 1)
        self.assertEqual(faixa_etaria("Gato", 12), 2)


class TestModelo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = ModeloRisco()

    def test_metricas_minimas(self):
        self.assertGreaterEqual(self.modelo.metricas["acuracia"], 0.85)
        self.assertGreaterEqual(self.modelo.metricas["validacaoCruzada5Folds"]["media"], 0.85)

    def test_probabilidades_somam_um(self):
        _, probabilidades = self.modelo.prever(39.1, 45, 58, 1, 1)
        self.assertAlmostEqual(sum(probabilidades.values()), 1.0, places=2)

    def test_idade_influencia_a_classificacao(self):
        _, adulto = self.modelo.prever(39.1, 45, 58, 0, 1)
        _, idoso = self.modelo.prever(39.1, 45, 58, 0, 2)
        self.assertGreaterEqual(calcular_irp(idoso), calcular_irp(adulto))


class TestTendencia(unittest.TestCase):
    def test_sem_historico(self):
        resultado = comparar_com_historico({"temperatura": 38.5, "atividade": 70, "alimentacao": 80, "irp": 0}, [])
        self.assertEqual(resultado["status"], "SEM_HISTORICO")

    def test_detecta_piora(self):
        historico = [{"temperatura": 38.4, "atividade": 80, "alimentacao": 90, "irp": 0} for _ in range(5)]
        atual = {"temperatura": 39.8, "atividade": 20, "alimentacao": 35, "irp": 10}
        resultado = comparar_com_historico(atual, historico)
        self.assertEqual(resultado["status"], "PIORA")
        self.assertEqual(len(resultado["alertas"]), 3)


if __name__ == "__main__":
    unittest.main()