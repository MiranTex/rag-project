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
- Neste caso é preciso OCR, que ainda não está nesta versão.

Chroma indisponível:
- Verificar se o container está up com docker compose ps.

## Próximos passos sugeridos

1. Adicionar OCR para PDFs digitalizados.
2. Adicionar streaming de resposta no chat.
3. Adicionar autenticação simples para múltiplos utilizadores.
4. Evoluir filtros por documento, período e tags.
