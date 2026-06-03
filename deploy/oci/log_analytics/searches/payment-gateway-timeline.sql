-- ============================================================================
-- payment-gateway-timeline
-- Real gateway emulator steps from checkout traces and app logs.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Payment Gateway Request ID' = '<GATEWAY_REQUEST_ID>',
-- 'Trace ID' = '<TRACE_ID>', or 'Order ID' = '<ORDER_ID>'.
-- ============================================================================
('Payment Gateway Request ID' != null or 'Payment Gateway Step' != null)
| sort Time
| fields Time, Service, 'Trace ID', 'Span ID', 'Order ID',
         'Payment Gateway Request ID', 'Payment Gateway Name',
         'Payment Method', 'Payment Network', 'Payment Card Brand',
         'Payment Wallet Type', 'Payment Gateway Step Index',
         'Payment Gateway Step', 'Payment Gateway Phase',
         'Payment Gateway Step Status', 'Payment Gateway Step Latency ms',
         'Payment Verification Provider', 'Payment Verification Decision',
         'Payment Processor Name', 'Payment Processor Decision',
         'Payment Status', 'Payment Risk Score', 'Original Log Content'
