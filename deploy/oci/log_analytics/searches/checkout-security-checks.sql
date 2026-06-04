-- ============================================================================
-- checkout-security-checks
-- Add-to-cart and checkout guardrail events emitted by security_span().
-- ============================================================================
('Security Check' != null or 'Security Event Classification' in ('mass_assign', 'rate_limit', 'idor'))
| where Time > dateRelative(2h)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('Trace ID') as Traces,
        values('Cart Product ID') as Products,
        values('Cart Quantity') as Quantities,
        values('Security Session ID') as Sessions,
        values('OWASP Category') as OWASP,
        values('MITRE Technique ID') as Techniques,
        values('Host IP Address (Client)') as 'Client IPs'
  by 'Security Endpoint', 'Security Check', 'Security Event Classification', 'Security Severity'
| sort -Events
