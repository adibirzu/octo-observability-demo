-- ============================================================================
-- user-order-action-correlation
-- Login, checkout, order, and payment pivots from real app logs.
-- Dashboard-safe: do not use LAQL colon parameters in saved searches.
-- To pivot manually, copy this query in Log Explorer and add literal filters
-- such as 'Trace ID' = '<TRACE_ID>', 'Auth User ID' = '<USER_ID>', or
-- 'Order ID' = '<ORDER_ID>'.
-- ============================================================================
('Auth User ID' != null or 'Order User ID' != null or 'Order ID' != null)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('Trace ID') as Traces,
        values('Auth Success') as 'Login Results',
        values('Auth Failure Reason') as 'Login Failure Reasons',
        values('Order ID') as Orders,
        values('Order Customer ID') as Customers,
        values('Payment Gateway Request ID') as 'Gateway Requests',
        values('Payment Status') as 'Payment Statuses',
        values('Security Check') as 'Security Checks'
  by 'Auth User ID', 'Auth Username', 'Auth Role', 'Order User ID'
| sort -'Last Seen'
