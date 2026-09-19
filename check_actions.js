/* Exercises the actionable-layer functions from static/index.html against a
 * realistic answer, so we know the mail draft and next steps actually produce
 * usable text rather than assuming they do.
 *
 * Run: node check_actions.js
 */

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(
  path.join(__dirname, 'static', 'index.html'), 'utf8');
const src = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// The script is written for a browser. Stub the few DOM touches the pure
// functions need, then evaluate it so we test the REAL code, not a copy.
const stubs = `
  const noop = () => {};
  const el = () => ({ style:{}, classList:{add:noop,remove:noop}, addEventListener:noop,
                      appendChild:noop, append:noop, setAttribute:noop, focus:noop,
                      select:noop, scrollIntoView:noop, insertAdjacentHTML:noop,
                      querySelector:() => null, children:[], innerHTML:'', textContent:'',
                      value:'', title:'', href:'', className:'', type:'', disabled:false });
  global.document = {
    getElementById: el, createElement: el, addEventListener: noop,
    querySelector: () => null, body: el(), title: '',
  };
  global.window = { location:{ href:'', search:'' } };
  global.location = { search:'', pathname:'/' };
  global.navigator = { clipboard:{ writeText: async () => {} } };
  global.URLSearchParams = class { constructor(){} get(){return null;} set(){} toString(){return '';} };
  global.fetch = () => Promise.resolve({ ok:true, json: async () => ({}) });
  global.setTimeout = () => 0;
`;

const sandbox = {};
const fn = new Function('exports', stubs + src + `
  exports.clean = clean;
  exports.nextSteps = nextSteps;
  exports.buildDraft = buildDraft;
  exports.sentences = sentences;
`);
fn(sandbox);

const { clean, nextSteps, buildDraft } = sandbox;

const ANSWER = `**Why the renewal is at risk**

- **July 9 P1 outage** — created commercial friction. Bluepeak's procurement now
  needs a justification to keep Kestrel as its sole analytics vendor.
- **Account health = Amber** — the deal moved from automatic rollover to a paper renewal.

**What we promised**

The meeting notes say we offered a **25% goodwill credit** on the July invoice.
Policy SLA-CREDIT-01 caps a sub-120-minute P1 credit at **10%**, and anything
above **20% requires CFO sign-off**, which has not been obtained.

| Item | Value |
|---|---|
| Contract value | USD 420,000 |
| Quoted renewal | USD 480,000 |`;

const SOURCES = [
  '03_meeting_2026-08-14_bluepeak_renewal.md',
  '05_policy_SLA-credit-01.md',
];

console.log('=== clean() ===');
console.log(clean(ANSWER).slice(0, 200));
console.log('\n=== nextSteps() ===');
nextSteps(ANSWER).forEach((s, i) => console.log(`  ${i + 1}. ${s}`));

console.log('\n=== buildDraft("email") ===');
console.log(buildDraft('email', 'Why is the Bluepeak renewal at risk?', ANSWER, SOURCES));

console.log('\n=== buildDraft("steps") ===');
console.log(buildDraft('steps', 'Q', ANSWER, SOURCES).slice(0, 400));

console.log('\n=== buildDraft("chat") ===');
console.log(buildDraft('chat', 'Renewal risk', ANSWER, SOURCES).slice(0, 300));

// Assertions: these are the things that would embarrass us on stage.
const email = buildDraft('email', 'Q', ANSWER, SOURCES);
const checks = [
  ['email has a Subject line', /^Subject: /m.test(email)],
  ['email keeps the real figures', email.includes('420,000') && email.includes('480,000')],
  ['email names the sources', email.includes('05_policy_SLA-credit-01.md')],
  ['email has no raw markdown bold', !email.includes('**')],
  ['email has no table pipes', !email.includes('|---')],
  ['next steps returned something', nextSteps(ANSWER).length > 0],
  ['chat draft strips markdown', !buildDraft('chat', 'Q', ANSWER, SOURCES).includes('**')],
];
console.log('\n=== assertions ===');
let bad = 0;
for (const [name, ok] of checks) {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  if (!ok) bad++;
}
process.exit(bad ? 1 : 0);
