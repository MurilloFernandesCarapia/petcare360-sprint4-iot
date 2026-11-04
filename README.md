# PetCare360 — Sprint 4

Projeto de demonstração de acompanhamento contínuo de pets com Node-RED, MQTT, API REST e serviço de IA em Python. O Random Forest e o IRP foram incluídos como protótipo acadêmico usando dados sintéticos; **não é um sistema clínico validado**.

## Conteúdo
- `PetCare360_3Sprint.json`: fluxo Node-RED atualizado para chamar o serviço Python.
- `ai_service/`: API FastAPI, Random Forest, cálculo do IRP, índice de atividade e consulta opcional a Oracle.
- `ARQUITETURA.md`: fluxo e configurações.
- `COMPONENTE_IA.md`: dados, algoritmo, fórmula do IRP, cálculo de atividade e limitações.
- `MATRIZ_REQUISITOS.md`: rastreabilidade dos itens da Sprint 4.
- `ROTEIRO_PITCH.md`: roteiro de apresentação de aproximadamente 5 minutos.
- `sql/`: SQL de referência do banco entregue na Sprint 3.
- `tests/`: testes unitários básicos.

## Requisitos
- Python 3.10 ou superior.
- Node-RED.
- Pacote `node-red-dashboard` para o dashboard legado.
- Broker MQTT acessível, se quiser demonstrar a parte IoT.
- Oracle é opcional para executar a API; é necessário para consultar medicação contínua diretamente da tabela `TB_MEDICAMENTO`.

## 1. Executar a IA
No terminal, a partir da pasta `PetCare360_Sprint4`:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate
pip install -r ai_service/requirements.txt
uvicorn ai_service.main:app --host 127.0.0.1 --port 8000
```

Verifique `http://127.0.0.1:8000/health`. O campo `demo_accuracy` é calculado sobre dados sintéticos de teste e **não** é métrica clínica.

## 2. Importar o fluxo Node-RED
1. Abra Node-RED no navegador.
2. Menu → Import → selecione `PetCare360_3Sprint.json`.
3. Instale `node-red-dashboard` caso os nós de dashboard não estejam disponíveis.
4. Clique em Deploy.
5. Abra `http://127.0.0.1:1880/ui`.
6. O serviço de IA deve estar rodando na porta 8000 antes de analisar um pet.

### Configurar endereços
O fluxo usa por padrão:
- API do Node-RED: `http://127.0.0.1:1880/api/ia/analisar`
- Serviço Python: `http://127.0.0.1:8000/api/ia/analisar`

Para mudar o serviço Python, defina `PETCARE360_AI_URL` no ambiente do processo Node-RED. Para mudar a URL da API usada pelo formulário, defina `PETCARE360_API_URL`. Reinicie o Node-RED após alterar variáveis de ambiente. Evite `localhost` quando os componentes estiverem em containers diferentes: use o nome do serviço/rede correto.

## 3. Testar a API

```bash
curl -X POST http://127.0.0.1:8000/api/ia/analisar \
  -H "Content-Type: application/json" \
  -d '{"petId":1,"nome":"Rex","especie":"Cão","raca":"Labrador","idade":5,"peso":28,"temperatura":39.8,"umidade":55,"atividade":20,"alimentacao":35,"comportamento":"Alterado"}'
```

A resposta contém `analiseIA.nivel`, `analiseIA.prioridade`/`irp`, probabilidades, motivos e recomendação.

### Dados de acelerômetro
A API também aceita `acelerometro` como uma lista de amostras XYZ em g. Exemplo reduzido:

```json
{"temperatura":38.3,"alimentacao":90,"comportamento":"Normal","acelerometro":[[0,0,1],[0.02,0,1],[0,0.03,1],[0,0,0.98]]}
```

Na demonstração do dashboard, o campo `atividade` continua sendo um percentual de entrada; só é calculado a partir do acelerômetro quando a API recebe amostras XYZ.

## 4. Oracle opcional para medicação
Configure `ORACLE_USER`, `ORACLE_PASSWORD` e `ORACLE_DSN` no ambiente do serviço Python. A consulta usa a tabela `TB_MEDICAMENTO` já existente no esquema da Sprint 3 e verifica se `DT_INICIO <= SYSDATE` e `DT_FIM` é nula ou futura. Nunca comite credenciais. Se Oracle não estiver configurado ou houver erro na consulta, o retorno será `medicamentoAtivoNoBanco: null`, que significa desconhecido — não significa que o pet não toma medicamento.

## 5. Testes
Com dependências instaladas, execute na raiz:

```bash
python -m unittest discover -s tests -v
```

## Limitações importantes
- O Random Forest é treinado com exemplos sintéticos gerados pelo código. A pontuação/acurácia de demonstração não pode ser interpretada como validação em animais reais.
- O mapeamento do acelerômetro é provisório e precisa ser calibrado com hardware real.
- A persistência automática de cada análise no Oracle não está implementada; o serviço consulta a tabela de medicamentos, mas não grava o resultado da análise.
- O sistema não diagnostica, não prescreve e não substitui um médico-veterinário.

## Checklist para entrega
- [ ] Importar e executar o fluxo Node-RED.
- [ ] Subir o serviço Python e confirmar `/health`.
- [ ] Testar os três níveis e registrar evidências reais do dashboard/API.
- [ ] Gravar o pitch, publicar como não listado e inserir o link no pacote final.
- [ ] Publicar o repositório GitHub com este README e os arquivos do projeto.
- [ ] Substituir ou completar os campos de integrantes/turma, se exigido pela disciplina.
