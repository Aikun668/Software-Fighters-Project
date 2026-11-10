const path = require('path');
const repoRoot = path.resolve(__dirname, '../../..');
const {chromium} = require('playwright');
(async()=>{
const browser=await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const source={conversationId:12,messageId:9,quote:'我在学习反向传播，它依赖链式法则。',createdAt:'2026-11-10'};
const nodes=['反向传播','链式法则','向量数据库'].map((title,i)=>({id:String(i),title,sources:[source],summary:'来自已保存的学习对话'}));
await page.route('http://localhost:5173/**', async r => {
 const fs=require('fs'),path=require('path'); const pathname=new URL(r.request().url()).pathname;
 const file=path.join(repoRoot, 'frontend/dist', pathname.startsWith('/assets/')?pathname:'index.html');
 await r.fulfill({contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file)});
});
await page.route('**/api/**',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({success:true,data:r.request().url().includes('/continuation')?{draft:'继续学习反向传播。依据：我在学习反向传播，它依赖链式法则。'}:r.request().url().includes('learning-map')?{nodes,edges:[{id:'e',source:'0',target:'1',relation:'depends_on',evidence:source}]}:[]})}));
await page.goto('http://localhost:5173/learning-resource-network');
await page.locator('[data-node="0"]').click();
await page.screenshot({path:path.join(__dirname, 'desktop-fixture.png'),fullPage:true});
await page.locator('[data-testid="local"]').click();if(await page.locator('[data-node]').count()!==2)throw Error('local count');
await page.locator('[data-testid="continue"]').click();
await page.waitForURL('**/question-nav-chat?**');
if(!(await page.locator('textarea').inputValue()).includes('反向传播'))throw Error('draft missing');
await page.screenshot({path:path.join(__dirname, 'chat-draft-fixture.png'),fullPage:true});
await page.setViewportSize({width:390,height:844});await page.goto('http://localhost:5173/learning-resource-network');await page.locator('[data-node="0"]').click();await page.screenshot({path:path.join(__dirname, 'mobile-fixture.png'),fullPage:true});
console.log('PASS desktop, local graph, draft handoff, mobile');await browser.close();
})();
