const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('shop/server/templates/shop.html', 'utf8');
const start = source.indexOf('function renderCheckoutEvidence(');
const end = source.indexOf('/* ── Dealers', start);
const buttons = [];
const panel = {hidden: true, innerHTML: '', querySelectorAll: () => buttons};
let copied = '';
let timer;
const context = {
    document: {getElementById: () => panel},
    esc: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    navigator: {clipboard: {writeText: async value => { copied = value; }}},
    setTimeout: callback => { timer = callback; },
    state: {checkoutInFlight: false},
    ensurePurchaseJourney: () => { throw new Error('stop before request'); },
};
vm.runInNewContext(source.slice(start, end), context);

async function testReceipt() {
    assert.match(source, /data-testid="checkout-evidence"[^>]*>\s*<h3>Checkout receipt<\/h3><p>No checkout evidence yet/);
    context.renderCheckoutEvidence(null);
    assert.equal(panel.hidden, false);
    assert.match(panel.innerHTML, /No checkout evidence yet/);
    const button = {
        textContent: 'Copy',
        getAttribute: () => 'trace-123',
        addEventListener: (event, handler) => { assert.equal(event, 'click'); button.click = handler; },
    };
    buttons.push(button);
    context.renderCheckoutEvidence({order_id: 'order-123', trace_id: 'trace-123', payment: {gateway: {request_id: 'gateway-123'}}});
    assert.match(panel.innerHTML, /Checkout receipt/);
    assert.match(panel.innerHTML, /Captured data pivots/);
    for (const value of ['order-123', 'trace-123', 'gateway-123']) assert.match(panel.innerHTML, new RegExp(value));
    await button.click();
    assert.equal(copied, 'trace-123');
    assert.equal(button.textContent, 'Copied');
    timer();
    assert.equal(button.textContent, 'Copy');
    context.navigator.clipboard.writeText = async () => { throw new Error('clipboard unavailable'); };
    await button.click();
    assert.equal(button.textContent, 'Select');
    timer();
    assert.equal(button.textContent, 'Copy');
    await assert.rejects(context.submitCheckout({preventDefault() {}}), /stop before request/);
    assert.match(panel.innerHTML, /No checkout evidence yet/);
    assert.doesNotMatch(panel.innerHTML, /trace-123/);
    context.renderCheckoutEvidence({});
    assert.match(panel.innerHTML, /not returned/);
}
testReceipt().catch(error => { console.error(error); process.exitCode = 1; });
