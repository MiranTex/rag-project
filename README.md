# RAG de Estudo com PDF, Chroma e LM Studio

Este projeto foi montado para estudo, com foco em execução local e aprendizagem passo a passo.

Arquitetura desta versão:
- LM Studio no host local, fora de Docker, em http://127.0.0.1:1234
- Chroma em Docker para base vetorial
- Backend em FastAPI
- Frontend em React

## Visão geral do fluxo RAG

1. Carregas um PDF.
2. O backend extrai texto por página.
3. O texto é dividido em chunks com sobreposição.
4. Cada chunk vira um embedding com modelo local HuggingFace.
5. Os vetores e metadados são gravados no Chroma.
6. Quando fazes uma pergunta, o sistema:
- gera embedding da pergunta,
- recupera os chunks mais próximos,
- monta um contexto,
- envia contexto + pergunta para o LM Studio,
- devolve resposta e fontes.

## Estrutura do projeto

- backend: API e serviços de ingestão e RAG
- frontend: interface web React
- tests: testes unitários iniciais
- data/uploads: PDFs carregados

## Aula 1: Preparar ambiente

Pré-requisitos:
- Python 3.11+
- Node 20+
- Docker e Docker Compose
- LM Studio já em execução no host

Se o comando `npm` não existir no sistema, instala Node.js e npm antes de continuar.

Passos:

1. Criar ambiente virtual Python na raiz do projeto.
2. Instalar dependências Python.
3. Copiar .env.example para .env.
4. Ajustar o nome do modelo de chat no campo LM_STUDIO_CHAT_MODEL para o nome real carregado no LM Studio.

Comandos:

```bash
cd /home/dev/Desktop/STUDY/RAG
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Aula 2: Subir a base vetorial

Subir apenas Chroma com Docker:

```bash
docker compose up -d
docker compose ps
```

O Chroma ficará disponível em http://127.0.0.1:8001 no host.

## Aula 3: Levantar backend

```bash
cd /home/dev/Desktop/STUDY/RAG
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

Endpoints principais:
- GET /health
- GET /documents
- POST /documents/upload
- POST /documents/{document_id}/reindex
- DELETE /documents/{document_id}
- POST /chat/ask

Teste rápido de saúde:

```bash
curl http://127.0.0.1:8000/health
```

## Aula 4: Levantar frontend React

```bash
cd /home/dev/Desktop/STUDY/RAG/frontend
npm install
npm run dev
```

Abrir no navegador:
- http://127.0.0.1:5173

## Aula 5: Primeiro ciclo completo

1. Abrir a interface.
2. Carregar o ficheiro memoria.pdf.
3. Esperar mensagem de indexação concluída.
4. Perguntar algo sobre o conteúdo do PDF.
5. Verificar se a resposta inclui fontes com página.

## Aula 5.1: Gestão de documentos

1. Reindexar documento: usa o botão Reindexar na lista de documentos na interface.
2. Apagar documento: usa o botão Apagar na lista de documentos na interface.
3. Reindexar por API:

```bash
curl -X POST http://127.0.0.1:8000/documents/<document_id>/reindex
```

4. Apagar por API:

```bash
curl -X DELETE http://127.0.0.1:8000/documents/<document_id>
```

## Aula 6: Testes iniciais

```bash
cd /home/dev/Desktop/STUDY/RAG
source .venv/bin/activate
pytest -q
```

## Aula 7: Histórico de chat persistente
@@ Mas respostas um pouco rasas motivaram melhorias na pipeline.
+
+ ## Aula 8: Streaming de respostas (SSE)
+
+ Implementa Server-Sent Events para geração de token-por-token em tempo real.
+ Adiciona `chat_stream()` ao LMStudioClient, novo endpoint `/chat/ask-stream`,
+ e parser SSE front-end. UTF-8 mojibake fixado.
+
+ ## Aula 9: Phase 3 - Re-ranking Avançado & Avaliação
+
+ ### Motivação
+
+ Após Phase 1 (chunking semântico) e Phase 2 (hybrid retrieval + prompt rigoroso),
+ identificámos que respostas podiam ser mais profundas e bem-fundamentadas.
+ A Phase 3 adiciona:
+
+ 1. **Re-ranking multi-fatorial**: Combina 5 sinais para ordenação final
+    - Vector similarity (60% peso): Relevância embeddings
+    - Keyword overlap (25%): Matching de termos da pergunta
+    - Position penalty (10%): Prefere chunks no início do doc (resumos/intros)
+    - Text density (5%): Favorece texto estruturado (listas) vs narrativa
+    - Recency boost (placeholder para future timestamp-based boost)
+
+ 2. **Framework de avaliação**: Dataset com questões de teste + métricas
+    - Localização: `tests/eval_data.json`
+    - Casos incluem: dificuldade (easy/medium/hard), palavras-chave esperadas
+    - Métricas: answer_depth, grounding, relevance com thresholds
+
+ 3. **Script de avaliação**: `backend/scripts/evaluate_rag.py`
+    - Executa todas questões de teste contra o pipeline
+    - Mede taxa de sucesso, performance por dificuldade, média de fontes
+    - Recomenda melhorias baseadas em resultados
+
+ ### Arquitetura nova
+
+ **Novo módulo**: `backend/services/reranker.py`
+ - `_compute_keyword_overlap(question, chunk)` → 0-0.25 score
+ - `_compute_position_penalty(chunk_idx, total)` → 0.5-1.0 penalty
+ - `_compute_text_density(text)` → 0.6-1.0 score
+ - `rerank_hybrid(question, candidates, weights=None)` → Lista ordenada com scores
+ - `RankingScores` dataclass: Breakdown de cada fator de scoring
+
+ **Modificação**: `backend/services/rag_pipeline.py`
+ - `build_user_prompt()` agora recupera top_k*2 candidatos
+ - Aplica `rerank_hybrid()` para re-ordenação com múltiplos fatores
+ - Seleciona top_k final com scores mais elevados
+ - Mantém backward-compatibility com `score_candidate()` (legado)
+
+ ### Exemplos de uso
+
+ Execute avaliação rápida:
+ ```bash
+ ./.venv/bin/python backend/scripts/evaluate_rag.py
+ ```
+
+ Com documento específico:
+ ```bash
+ ./.venv/bin/python backend/scripts/evaluate_rag.py --document-id <doc_id>
+ ```
+
+ Customizar pesos de re-ranking:
+ ```python
+ from backend.services.reranker import rerank_hybrid
+
+ custom_weights = {
+     'vector': 0.5,     # Menos peso em embeddings
+     'keyword': 0.35,   # Mais peso em keywords
+     'position': 0.1,
+     'density': 0.05,
+ }
+ reranked = rerank_hybrid(question, candidates, weights=custom_weights)
+ ```
+
+ ### Testes & Validação
+
+ `tests/test_reranker.py`: 18 casos cobrindo
+ - Keyword overlap (case-insensitive, empty query, high/low overlap)
+ - Position penalty (early/middle/late chunks, single chunk)
+ - Text density (punctuation-dense, long narrative, moderate, empty)
+ - Full re-ranking pipeline (sort order, score breakdown, custom weights)
+
+ Status: **24 testes passam** (incluindo 18 novos para re-ranker)
+
+ ### Performance esperada
+
+ Com Phase 1-3 completas, espera-se:
+ - Chunks não cortados mid-sentença → compreensão melhor pelo LLM
+ - Retrieval re-ordenado por relevância combinada → chunks top-k mais precisos
+ - Prompt rigoroso → respostas cite fontes e respeitem contexto
+ - **Resultado**: Respostas mais profundas, bem-fundamentadas, e verificáveis
+
+ &nbsp;

1. O chat guarda automaticamente as perguntas e respostas no browser (localStorage).
2. Ao atualizar a página, o histórico volta a aparecer.
3. Botão Exportar histórico: descarrega um ficheiro JSON com perguntas, respostas e fontes.
4. Botão Limpar histórico: remove o histórico da sessão no browser.

Nota: no campo de pergunta, Enter envia a pergunta e Shift+Enter cria nova linha.

## Aula 8: Streaming de resposta em tempo real

1. O endpoint `POST /chat/ask-stream` envia eventos SSE em tempo real.
2. O frontend consome o stream e atualiza a resposta token a token.
3. Os eventos emitidos são:
- `sources`: fontes recuperadas no Chroma.
- `token`: fragmento de texto da resposta.
- `done`: resposta final consolidada.
- `error`: erro durante geração.

Teste rápido por terminal:

```bash
curl -N -X POST http://127.0.0.1:8000/chat/ask-stream \
	-H "Content-Type: application/json" \
	-d '{"question":"Resumo curto do documento em 2 frases.","top_k":3}'
```

## Aula 10: A/B de Re-ranking e Grounding

O backend suporta dois perfis de pesos de re-ranking configuráveis por ambiente:

- `RERANK_WEIGHTS_DEFAULT`: perfil equilibrado (vector-first)
- `RERANK_WEIGHTS_GROUNDING`: perfil com mais peso em keyword/posição para melhorar ancoragem

Variáveis em `.env`:

```env
RERANK_WEIGHTS_DEFAULT={"vector": 0.60, "keyword": 0.25, "position": 0.10, "density": 0.05}
RERANK_WEIGHTS_GROUNDING={"vector": 0.45, "keyword": 0.30, "position": 0.20, "density": 0.05}
```

Executar avaliação simples:

```bash
./.venv/bin/python backend/scripts/evaluate_rag.py --document-id <document_id>
```

Executar comparação A/B dos perfis:

```bash
./.venv/bin/python backend/scripts/evaluate_rag.py --document-id <document_id> --ab
```

No modo A/B, o script corre o dataset duas vezes (`A/default` e `B/grounding`) e mostra os deltas de `grounding`, `relevance`, `depth` e taxa de sucesso.

## Erros comuns e solução

LM Studio não responde:
- Confirmar que está ativo no host.
- Confirmar URL base no .env.

Modelo de chat inválido:
- Ajustar LM_STUDIO_CHAT_MODEL para o nome exato mostrado em /v1/models.

PDF sem texto:
- Alguns PDFs são apenas imagem.
- As páginas sem texto passam por OCR (ver Aula 11) e aparecem na revisão com alerta (ver Aula 13).

Chroma indisponível:
- Verificar se o container está up com docker compose ps.

## Próximos passos sugeridos

1. Adicionar autenticação simples para múltiplos utilizadores.
2. Evoluir filtros por documento, período e tags.

## Aula 11: OCR para PDFs digitalizados

Páginas sem camada de texto (digitalizações) passam por OCR com Tesseract (`por+eng`):

1. O pypdf tenta extrair o texto de cada página.
2. Páginas com menos de `OCR_MIN_TEXT_CHARS` caracteres são renderizadas a `OCR_DPI` (pypdfium2) e enviadas ao Tesseract, em paralelo.
3. O texto do OCR é limpo: junta palavras hifenizadas na quebra de linha e remove linhas de ruído (bordas, carimbos).
4. A confiança média do Tesseract fica nos logs (`make logs`) e nos metadados de cada chunk (`extraction`, `ocr_confidence`). Abaixo de `OCR_MIN_CONFIDENCE` aparece um aviso para rever o texto.

Variáveis: `OCR_ENABLED`, `OCR_LANGUAGES`, `OCR_DPI`, `OCR_MIN_TEXT_CHARS`, `OCR_MIN_CONFIDENCE`, `OCR_MAX_WORKERS`.

Para documentos já indexados antes do OCR, usar o endpoint `POST /documents/{id}/reindex`.

## Aula 12: Agente com tools

Além do chat RAG, existe um modo **Agente**. O modelo decide que ferramentas usar (pesquisar, ler páginas, calcular, exportar), vê os resultados e repete até ter a resposta. A pesquisa no RAG passa a ser uma das tools ("agentic RAG").

### Componentes

| Camada | Ficheiro | Responsabilidade |
|---|---|---|
| Orquestração | `backend/agent/runner.py` | Loop do agente: chama o LLM, executa `tool_calls`, devolve resultados, força resposta no último passo (`AGENT_MAX_STEPS`). Emite eventos. |
| Perfis | `backend/agent/profiles.py` | Prompt de sistema + conjunto de tools por contexto (`assistente`, `consulta`). |
| Eventos | `backend/agent/events.py` | `thinking`, `tool_call`, `tool_result`, `export`, `sources`, `answer` (enviados por SSE). |
| Tools | `backend/agent/tools/` | `base.py` (Tool, registo, contexto), `documents.py`, `calculations.py`, `exports.py`. |
| Serviços | `backend/services/export_store.py`, `document_writer.py` | Guardar ficheiros exportados (sem sobrescrever) e gerar CSV/Markdown/Word. |
| API | `backend/api/agent.py`, `backend/api/exports.py` | `GET /agent/profiles`, `POST /agent/ask-stream`, `GET /exports`, `GET /exports/{nome}`. |
| Frontend | `AgentSteps.jsx`, `ExportLinks.jsx`, `Markdown.jsx` | Passos do agente ao vivo, links de download, respostas em markdown. |

### Tools disponíveis

- **Documentos:** `list_documents`, `search_documents` (pesquisa híbrida), `read_document` (texto completo por página).
- **Cálculo:** `calculate` (expressões aritméticas, avaliadas sem `eval`), `percentage_change`, `date_difference`, `date_add`.
- **Exportação** (`side_effect=True`): `export_csv` (`;` + BOM, abre no Excel), `export_document` (`.docx` ou `.md`). Os ficheiros ficam em `data/exports/`.

### Criar uma tool nova

1. Num módulo em `backend/agent/tools/`, define os parâmetros (Pydantic) e a função:

   ```python
   class MyParams(BaseModel):
       value: str = Field(description="...")  # a descrição chega ao modelo

   @tool(name="my_tool", description="O que faz e quando usar.", params=MyParams)
   def my_tool(params: MyParams, ctx: ToolContext) -> ToolResult:
       return ToolResult(content={...}, summary="linha curta para a UI")
   ```

2. Adiciona-a a `ALL_TOOLS` em `backend/agent/tools/__init__.py`.
3. Se só fizer sentido em alguns contextos, inclui-a no `tool_names` do perfil certo em `profiles.py`.

Erros esperados devem levantar `ToolError`. A mensagem é devolvida ao modelo para ele corrigir o pedido.

### Guarda de âmbito

Antes do agente, um modelo pequeno (`GUARD_MODEL`, por defeito Haiku) classifica cada mensagem numa categoria (`backend/agent/guard.py`):

| Categoria | Por defeito |
|---|---|
| `documentos`, `seguimento`, `assistente`, `conversa`, `conhecimento_geral`, `calculo` | permitida |
| `fora_do_ambito` (jogos, escrita criativa, programação, temas não relacionados, tentativas de mudar as regras) | bloqueada com mensagem fixa, sem acionar o agente |

- O modelo só classifica; **quem decide o bloqueio é o perfil** (`AgentProfile.blocked_categories`), por isso a política é explícita e configurável.
- O guarda vê as últimas trocas, para perceber seguimentos ("e em percentagem?") e para bloquear a continuação de conversas fora do âmbito.
- Se o guarda falhar, o pedido é permitido (fail-open) e fica um aviso nos logs. O âmbito no prompt do agente é a segunda linha de defesa: em pedidos mistos responde só à parte do âmbito, e ignora instruções que apareçam dentro dos documentos.
- `GUARD_ENABLED=false` desativa o guarda.

## Aula 13: Revisão do texto antes de indexar

A indexação passou a ter duas fases, com uma validação entre elas:

1. **Extração** (`POST /documents/upload`, `POST /documents/{id}/reindex`): pypdf + OCR. O texto de cada página fica em `backend/storage/extractions/{id}.json` e o documento fica `pending_review`, fora do Chroma e do índice de palavras-chave.
2. **Validação automática** (`backend/services/extraction_review.py`): cada página recebe alertas:
   - `empty`: sem texto;
   - `short`: menos de `OCR_MIN_TEXT_CHARS` caracteres;
   - `low_confidence`: OCR com confiança abaixo de `OCR_MIN_CONFIDENCE`;
   - `garbled`: mais de `REVIEW_MAX_GARBLED_RATIO` das palavras parecem mal lidas (símbolos no meio, letras sem vogais);
   - `encoding`: `�`, mojibake (`Ã©`) ou glifos `(cid:N)`.
3. **Revisão humana** (botão **Rever** no frontend): editar o texto de uma página, excluí-la, ou repetir o OCR com outro DPI.
4. **Aprovação** (`POST /documents/{id}/approve`): chunks, embeddings e indexação do texto revisto. Os chunks levam `extraction` (`text`, `ocr`, `manual`) e `edited` nos metadados.

Com `AUTO_APPROVE_CLEAN_DOCUMENTS=true`, os documentos sem alertas saltam o passo 3 e são indexados logo. Os que têm alertas ficam sempre à espera de revisão. Por defeito está `false`: todos os documentos passam pela revisão.

| Endpoint | Descrição |
|---|---|
| `GET /documents/{id}/extraction` | Texto, origem, confiança e alertas por página |
| `PUT /documents/{id}/pages/{n}` | `{"text": "..."}` e/ou `{"excluded": true}` |
| `POST /documents/{id}/pages/{n}/ocr` | `{"dpi": 400}` repete o OCR da página |
| `POST /documents/{id}/approve` | Indexa o texto revisto |

Só se edita um documento `pending_review`. Para rever um documento já indexado, usar reindex: volta a extrair do zero (as edições manuais perdem-se) e o documento sai do índice até nova aprovação. Documentos indexados antes desta fase não têm extração guardada; aparecem como indexados e precisam de reindex para serem revistos.

## Aula 14: Ficha do documento, tipos e secções

Cada documento passa a ter uma ficha e cada excerto passa a saber de que secção vem. Tudo é proposto na extração e confirmado no ecrã de revisão.

O sistema não é específico de nenhum domínio. Cada instituição define os seus **tipos de documento** em `backend/document_types.json`, ou noutro ficheiro indicado em `DOCUMENT_TYPES_FILE`. O ficheiro de exemplo traz três tipos:

| Tipo | Campos próprios | Secções reconhecidas |
|---|---|---|
| `generic` (Documento, o tipo por defeito) | Entidade | Resumo, Introdução, Conclusões, Referências, Anexos |
| `academic` (Trabalho académico) | Orientadores, Curso, Instituição | Resumo, Introdução, Estado da arte, Metodologia, Resultados, Conclusões, Trabalho futuro, Limitações, Referências, Anexos |
| `procedure` (Procedimento) | Código, Área responsável, Versão | Objetivo, Âmbito, Definições, Responsabilidades, Procedimento, Referências, Anexos |

Para outro domínio (contratos, atas, relatórios de auditoria...), acrescenta-se um tipo ao ficheiro:

```json
"minutes": {
  "label": "Ata",
  "description": "Atas de reuniões de órgãos e equipas.",
  "fields": [
    {"key": "body", "label": "Órgão", "type": "text", "filterable": true},
    {"key": "attendees", "label": "Presentes", "type": "people"}
  ],
  "sections": [
    {"key": "agenda", "label": "Ordem de trabalhos", "patterns": ["ordem de trabalhos", "agenda"]},
    {"key": "decisions", "label": "Deliberações", "patterns": ["delibera[çc][õo]es", "decis[õo]es"]}
  ]
}
```

- **Núcleo comum a todos os tipos:** título, autores, ano, palavras-chave e resumo. Os campos próprios de cada tipo ficam em `fields`.
- **Tipos de campo:** `text`, `list` e `people` (lista de nomes, a que se tiram títulos como Prof. ou Dr.).
- **`filterable`:** o campo vai para os metadados de cada excerto e pode filtrar pesquisas. Só se aplica a campos `text`.
- **Padrões de secção:** são regex Python, sem distinção entre maiúsculas e minúsculas, comparadas com a linha inteira depois de tirar a numeração ("2.", "5.1", "Capítulo 3").
- **Secções com papel especial:** a secção `abstract` dá o resumo e `references` dá a bibliografia.
- **Comum a qualquer tipo:** os elementos iniciais (índice, listas, agradecimentos) e os capítulos numerados sem nome conhecido ("3 Arquitetura do sistema" fica `chapter`).
- **Entradas de índice:** as linhas com reticências, ou do tipo "Título 12" depois de um título "Índice", não contam como títulos.
- **Contador de página:** o "16/80 2 COVID – 19" que o pypdf cola à primeira linha é ignorado.
- **Documentos sem estrutura:** com menos de 2 títulos, o documento fica sem secções.
- **Quebras de linha:** a extração passou a preservá-las, porque os títulos só se reconhecem linha a linha.

**Proposta da ficha** (`backend/services/metadata_extraction.py`):
- O modelo pequeno (`GUARD_MODEL`, o mesmo da guarda) escolhe o tipo e propõe título, autores, ano e os campos desse tipo, numa só chamada a partir das 3 primeiras páginas. Este modelo aceita `tool_choice` forçado, que alguns modelos de chat recusam.
- Resumo, palavras-chave e referências saem do texto por regras, com as secções do tipo escolhido.
- Se o modelo falhar, fica o tipo por defeito e só a parte das regras.
- `KNOWLEDGE_BASE_DESCRIPTION` é uma frase sobre a base de conhecimento ("Repositório de trabalhos finais de curso da Escola X", "Normas internas da Câmara Y"). É usada nos prompts da ficha, da guarda e do agente.

**Na aprovação**:
- Cada chunk leva `section`, `document_type` e, quando preenchidos, `title`, `year` e os campos `filterable` do tipo.
- As referências são gravadas a partir do texto revisto.

| Endpoint | Descrição |
|---|---|
| `GET /documents/types` | Tipos configurados (o primeiro é o tipo por defeito) |
| `GET /documents/{id}/extraction` | Inclui `metadata`, `sections` (títulos detetados) e `references` |
| `PUT /documents/{id}/metadata` | Grava a ficha; ao mudar de tipo, os campos que o novo tipo não tem desaparecem |
| `POST /documents/{id}/metadata/suggest` | Pede nova proposta ao modelo; só preenche campos vazios |

Variáveis: `METADATA_EXTRACTION_ENABLED`, `DOCUMENT_TYPES_FILE` e `KNOWLEDGE_BASE_DESCRIPTION`.

Documentos indexados antes desta aula não têm ficha nem secções. Para os ter, é preciso extrair de novo (reindex).
