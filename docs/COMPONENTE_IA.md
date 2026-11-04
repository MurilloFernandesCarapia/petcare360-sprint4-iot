# Componente de IA — PetCare360 Sprint 4

## Problema

Tutores percebem mudanças no pet (come menos, está parado, parece quente), mas não sabem se aquilo merece contato com a clínica. A clínica recebe muitos contatos e não tem como priorizar. A IA transforma as leituras da coleira e as observações do tutor em uma prioridade objetiva, explicada e personalizada para cada pet.

## Abordagem

Classificação supervisionada com **Random Forest** (`scikit-learn`), escolhida por funcionar bem com poucas features tabulares, devolver probabilidades por classe (usadas no IRP) e oferecer importância das features para explicar o modelo.

| Hiperparâmetro | Valor |
|---|---|
| `n_estimators` | 200 |
| `max_depth` | 10 |
| `min_samples_leaf` | 3 |
| `class_weight` | `balanced` |
| `random_state` | 42 |

## Dados

| Feature | Origem | Tratamento |
|---|---|---|
| `temperatura` | Sensor da coleira ou formulário | °C, validado entre 25 e 45 |
| `atividade` | Acelerômetro (XYZ) ou formulário | Índice 0–100 |
| `alimentacao` | Registro do comedouro/tutor | Percentual 0–100 da porção habitual |
| `comportamento_alterado` | Observação do tutor | 0 ou 1 |
| `faixa_etaria` | `TB_PET.DT_NASCIMENTO` + espécie | 0 filhote (< 1 ano), 1 adulto, 2 idoso (cão ≥ 7, gato ≥ 10) |

Como não há base real rotulada de pets, o treino usa **3.000 amostras sintéticas** geradas em `gerar_dados_sinteticos`. Os rótulos seguem uma regra de pontuação de triagem (temperatura, atividade, alimentação, comportamento e faixa etária mais sensível) e as features recebem ruído de sensor (±0,15 °C na temperatura, ±5 pontos em atividade e alimentação). O ruído faz com que leituras próximas dos limites fiquem ambíguas, como acontece com sensores reais, e impede que o modelo apenas decore a regra.

Divisão: 80% treino, 20% teste, estratificada por classe.

## Avaliação

| Métrica | Valor |
|---|---|
| Acurácia no teste | 0,898 |
| Validação cruzada (5 folds) | 0,893 ± 0,014 |

| Classe | Precisão | Recall | F1 |
|---|---|---|---|
| NORMAL | 0,912 | 0,901 | 0,906 |
| ATENÇÃO | 0,853 | 0,903 | 0,878 |
| ALTO | 0,947 | 0,891 | 0,918 |

Matriz de confusão (linhas = real, colunas = previsto, ordem NORMAL / ATENÇÃO / ALTO):

```
NORMAL    145   15    1
ATENÇÃO    14  215    9
ALTO        0   22  179
```

Nenhum caso real `ALTO` foi classificado como `NORMAL`, que é o erro mais grave nesse contexto. Os erros se concentram entre classes vizinhas. Todas essas métricas ficam disponíveis em tempo real no endpoint `GET /api/ia/modelo`.

## IRP — Índice de Risco/Prioridade

```
IRP = arredondar(10 × (0,5 × P(ATENÇÃO) + 1,0 × P(ALTO)))      limitado a 0–10
```

O IRP usa a confiança do modelo, não só a classe. Duas leituras classificadas como `ATENÇÃO` podem ter IRP 4 ou 7, dependendo de quanto a probabilidade de `ALTO` pesa, o que permite à clínica ordenar os pacientes. Exemplos: 100% NORMAL → 0; 100% ATENÇÃO → 5; 100% ALTO → 10.

## Índice de atividade pelo acelerômetro

Para cada amostra `[x, y, z]` em g:

1. magnitude = √(x² + y² + z²)
2. componente dinâmica = desvio-padrão de (magnitude − 1 g) na janela
3. atividade = (dinâmica − 0,02) / (0,60 − 0,02) × 100, limitada a 0–100

O simulador envia 50 amostras por leitura, com amplitude diferente para cada cenário, e o dashboard mostra a atividade calculada a partir delas.

## Personalização

- **Perfil do banco**: com `petId`, o serviço busca espécie, raça, peso e idade em `TB_PET`, a mesma tabela usada pelo app mobile. A idade vira a feature `faixa_etaria`, então o mesmo conjunto de sinais pode gerar uma prioridade maior para um pet idoso ou filhote.
- **Medicamentos**: medicamentos ativos em `TB_MEDICAMENTO` entram nos motivos e na recomendação.
- **Recomendação**: texto base por nível mais orientações específicas para faixa etária, medicação e tendência do próprio pet.

## Acompanhamento contínuo

Antes de gravar a nova análise, o serviço busca as últimas 5 análises do pet em `TB_ANALISE_IA` e calcula a variação da leitura atual em relação à média delas:

| Regra | Resultado |
|---|---|
| Temperatura ≥ +0,5 °C | Alerta de temperatura acima do padrão do pet |
| Atividade ≤ −20 pontos | Alerta de atividade abaixo do padrão do pet |
| Alimentação ≤ −20 pontos | Alerta de alimentação abaixo do padrão do pet |
| IRP ≥ +2 | Tendência `PIORA` |
| IRP ≤ −2 | Tendência `MELHORA` |
| Demais casos | Tendência `ESTAVEL` |

Assim a IA não compara o pet só com limites gerais, mas com o padrão dele mesmo.

## Limitações

- Base sintética: as métricas mostram que o pipeline funciona, não que o modelo acerta em animais reais. O próximo passo seria treinar com registros rotulados por veterinários da CLYVO VET.
- Limites de faixa etária e de temperatura são simplificados e iguais para todas as raças.
- A calibração do acelerômetro depende do hardware e da frequência de amostragem reais.
- O sistema é apoio à decisão e não emite diagnóstico.