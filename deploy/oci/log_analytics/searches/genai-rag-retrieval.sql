-- GenAI RAG retrieval analytics (G6): grounding quality of the 23ai VECTOR search.
-- Reads the retrieval.embed + vector_db.search spans (added with the RAG agent):
-- how many passages were retrieved, the closest cosine distance, and the top_k used.
-- A rising empty-retrieval count = poor grounding / unseeded KB. Source: octo-genai-studio.
'Log Source' = 'octo-genai-studio'
| where 'vector.metric' != null or 'retrieval.documents.count' != null
| stats count as searches,
        avg('retrieval.documents.count') as avg_docs,
        sum(case('retrieval.documents.count' = 0, 1, 1 = 1, 0)) as empty_retrievals,
        avg('retrieval.top_distance') as avg_top_distance,
        avg('vector.top_k') as avg_top_k
   by 'studio.data_source', 'vector.metric'
| sort -searches
-- (visualization inferred: table)
