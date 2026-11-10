// Real controller + H2 integration. Requires the backend JSON-lines bridge command.
const path=require('path'), fs=require('fs'), {spawn}=require('child_process'), readline=require('readline');
const {chromium}=require('playwright');
const repoRoot=path.resolve(__dirname,'../../..');
if(!process.env.LEARNING_MAP_BRIDGE_COMMAND) throw Error('Set LEARNING_MAP_BRIDGE_COMMAND to the backend bridge launcher');
const bridge=spawn(process.env.LEARNING_MAP_BRIDGE_COMMAND,{cwd:path.join(repoRoot,'backend'),shell:true,stdio:['pipe','pipe','inherit']});
const waiting=[];
readline.createInterface({input:bridge.stdout}).on('line',line=>{try{const value=JSON.parse(line.startsWith('MAP_RESULT ')?line.slice(11):line); if(value.status!==undefined)waiting.shift()?.resolve(value);else console.error(line)}catch{console.error(line)}});
bridge.on('exit',code=>{while(waiting.length)waiting.shift().reject(Error(`Bridge exited ${code}`))});
let queue=Promise.resolve();
function api(method,url,body){console.error('API',method,url);const run=()=>new Promise((resolve,reject)=>{waiting.push({resolve,reject});bridge.stdin.write(JSON.stringify({method,path:url,body})+'\n')});const result=queue.then(run);queue=result.catch(()=>{});return result;}
(async()=>{
let browser;
try{
browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE||undefined,headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
await page.route('http://localhost:5173/**',async r=>{const pathname=new URL(r.request().url()).pathname;const file=path.join(repoRoot,'frontend/dist',pathname.startsWith('/assets/')?pathname:'index.html');await r.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file)})});
await page.route('**/api/**',async r=>{const url=new URL(r.request().url()); if(!url.pathname.startsWith('/api/learning-map'))return r.fulfill({contentType:'application/json',body:JSON.stringify({success:true,data:[]})});const result=await api(r.request().method(),url.pathname,r.request().postDataJSON());await r.fulfill({status:result.status,contentType:'application/json',body:typeof result.body==='string'?result.body:JSON.stringify(result.body)})});
const unwrap=result=>{const body=typeof result.body==='string'?JSON.parse(result.body):result.body;return body.data??body};
await page.goto('http://localhost:5173/learning-resource-network');await page.locator('[data-node]').first().waitFor();
await page.locator('[data-testid="tab-events"]').click();await page.locator('.record').first().waitFor();
await page.screenshot({path:path.join(__dirname,'trajectory-real-api.png'),fullPage:true});
const map=unwrap(await api('GET','/api/learning-map'));
const pending=(map.suggestions||[]).filter(s=>s.status==='pending'); if(pending.length<2)throw Error('Bridge must seed at least two genuine candidate suggestions');
await page.locator('[data-testid="tab-suggestions"]').click();
await page.locator(`[data-testid="accept-${pending[0].id}"]`).click();await page.getByText('已确认的探索关联',{exact:true}).waitFor();
await page.locator(`[data-testid="reject-${pending[1].id}"]`).click();await page.getByText('已拒绝此建议',{exact:true}).waitFor();
await page.reload();await page.locator('[data-testid="tab-suggestions"]').click();await page.getByText('已确认的探索关联',{exact:true}).waitFor();await page.getByText('已拒绝此建议',{exact:true}).waitFor();
const after=unwrap(await api('GET','/api/learning-map'));
if(!after.edges.some(e=>e.relation==='user_confirmed'))throw Error('Accepted association not persisted');
await page.screenshot({path:path.join(__dirname,'suggestions-real-api.png'),fullPage:true});
await page.locator(`[data-testid="change-${pending[0].id}"]`).click();
await page.locator(`[data-testid="change-${pending[0].id}"]`).filter({hasText:'重新确认'}).waitFor();
const withdrawn=unwrap(await api('GET','/api/learning-map'));
if(withdrawn.edges.some(e=>e.relation==='user_confirmed'))throw Error('Withdrawn association edge remains');
await page.locator(`[data-testid="change-${pending[0].id}"]`).click();
await page.getByText('已确认的探索关联',{exact:true}).waitFor();

await page.getByRole('button',{name:'知识地图',exact:true}).click();await page.locator('[data-node]').first().click();
await page.locator('[data-testid="continue"]').click();await page.waitForURL(url=>url.pathname==='/question-nav-chat');
if(new URL(page.url()).searchParams.has('draft'))throw Error('Private context leaked into URL');
const draft=await page.locator('textarea').inputValue();if(draft.length<50)throw Error('Continuation lacks source context');
await page.screenshot({path:path.join(__dirname,'continuation-real-api.png'),fullPage:true});
console.log(JSON.stringify({pass:true,checks:['real-controller-map','evidence-events','accept-reject-persist-after-reload','user-confirmed-not-fact','live-context-draft-no-send','withdraw-and-reconfirm'],draftLength:draft.length}));
}finally{await browser?.close();bridge.stdin.end();bridge.kill();}
})().catch(e=>{console.error(e);process.exitCode=1});
