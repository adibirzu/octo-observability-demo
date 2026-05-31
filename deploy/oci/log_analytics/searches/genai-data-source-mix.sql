-- AI Studio Sales Analyst data-source mix: live Oracle ATP vs synthetic fallback.
-- A health signal — if synthetic climbs, the read-only ATP path (studio_ro) is
-- failing; the fallback reason is on the tool.atp_query span.
-- Source: octo-genai-studio studio.data_source attribute in Log Analytics.
'Log Source' = 'octo-genai-studio'
| where 'studio.data_source' != null
| stats count as runs by 'studio.data_source'
-- (visualization inferred: pie)
