# RAG pipeline module map — every module below implements exactly one stage,
# so no LLM call in this app ever receives full/raw document text:
#
#   Document Parsing + Chunking -> agents/parser_agent.py
#   Embedding                   -> utils/llm_client.get_embeddings
#   Vector Store                -> vectorstore/chroma_client.py
#   Retrieval                   -> services/retrieval_service.py
#   Prompt Builder              -> services/prompt_builder.py
#   LLM Service                 -> utils/llm_client.py
