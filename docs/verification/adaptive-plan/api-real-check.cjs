const assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'../../..');
const bridge=require('./bridge-client.cjs')(process.env.ADAPTIVE_PLAN_BRIDGE_COMMAND,path.join(root,'backend'));
const checks=[];
async function call(method,url,body,status=200,user='1'){
 const r=await bridge.api(method,url,body,user);assert.equal(r.status,status,JSON.stringify(r));
 if(status===200)assert.equal(r.body.code,0,JSON.stringify(r));return r.body.data;
}
const tasks=p=>p.modules.flatMap(m=>m.tasks),minutes=p=>tasks(p).reduce((sum,t)=>sum+t.minutes,0);
(async()=>{try{
 let p=await call('POST','/api/adaptive-plans',{title:'数据库事务学习',goal:'理解事务隔离与幻读',dailyMinutes:45,modules:[{title:'事务基础',tasks:[{title:'复习事务',minutes:15,nextAction:'阅读笔记'},{title:'理解幻读',minutes:45,nextAction:'复现例子'},{title:'对比隔离级别',minutes:30}]},{title:'索引进阶',tasks:[]}]});
 const url='/api/adaptive-plans/'+p.id;const completed=tasks(p)[0].id;
 assert.deepEqual(await call('GET',url),p);checks.push('creation-roundtrip');
 p=await call('PATCH',url+'/tasks/'+completed,{version:p.version,status:'completed'});
 const target=tasks(p)[1].id;
 p=await call('PATCH',url+'/tasks/'+target,{version:p.version,status:'paused',checkpoint:'做到幻读示例第二步',nextAction:'打开第二个事务插入一行'});
 assert.equal(tasks(await call('GET',url))[1].checkpoint,'做到幻读示例第二步');checks.push('pause-checkpoint-persists');
 const before=JSON.parse(JSON.stringify(p));
 let proposal=await call('POST',url+'/proposals',{version:p.version,message:'每天只有20分钟，拆分任务',dailyMinutes:20});
 assert.deepEqual(await call('GET',url),before);checks.push('proposal-and-cancel-do-not-mutate');
 p=await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version});
 assert.equal(minutes(p),minutes(before));assert.deepEqual(tasks(p)[0],tasks(before)[0]);assert.ok(p.nextTasks.length<=3);checks.push('confirm-split-preserves-effort-completed-and-bounded-next');
 await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:before.version},409);
 await call('GET',url,undefined,404,'2');await call('PATCH',url+'/tasks/'+target,{version:p.version,status:'completed'},404,'2');await call('GET',url,undefined,401,'anonymous');assert.deepEqual(await call('GET','/api/adaptive-plans',undefined,200,'2'),[]);await call('POST',url+'/proposals',{version:p.version,message:'每天20分钟'},404,'2');await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version},404,'2');await call('POST',url+'/undo',{version:p.version},404,'2');checks.push('repeat-stale-and-ownership-rejected');
 p=await call('POST',url+'/undo',{version:p.version});assert.deepEqual(p.modules,before.modules);assert.equal(p.dailyMinutes,before.dailyMinutes);checks.push('undo-restores-plan');
 proposal=await call('POST',url+'/proposals',{version:p.version,message:'每天20分钟',dailyMinutes:20});p=await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version});
 p=await call('PATCH',url+'/tasks/'+target,{version:p.version,status:'in_progress'});
 await call('POST',url+'/undo',{version:p.version},409);checks.push('resume-prevents-old-undo-overwrite');
 proposal=await call('POST',url+'/proposals',{version:p.version,message:'每天20分钟',dailyMinutes:20,deadline:'2000-01-01'});assert.ok(proposal.conflict);
 await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version},400);
 p=await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version,resolution:'extend'});assert.ok(p.deadline>'2000-01-01');checks.push('deadline-explicit-resolution');
 const oldTotal=minutes(p);p=await call('POST',url+'/modules/'+p.modules[1].id+'/tasks',{version:p.version,title:'执行计划',minutes:15,nextAction:'运行 explain'});assert.equal(p.modules[1].tasks[0].title,'执行计划');assert.equal(minutes(p),oldTotal+15);assert.ok(p.nextTasks.length<=3);assert.equal(p.status,'in_progress');checks.push('empty-module-refinement-persists');const deferred=p.modules[1].tasks[0].id;proposal=await call('POST',url+'/proposals',{version:p.version,message:'延期执行计划',taskId:deferred});p=await call('POST',url+'/proposals/'+proposal.id+'/apply',{version:p.version,resolution:'extend'});const deferredTotal=minutes(p);p=await call('PATCH',url+'/tasks/'+deferred,{version:p.version,status:'pending'});assert.equal(p.modules[1].tasks[0].status,'pending');assert.equal(minutes(p),deferredTotal);checks.push('deferred-reactivation-preserves-work');console.log(JSON.stringify({pass:true,checks},null,2));
}finally{bridge.close()}})().catch(e=>{console.error(e);process.exitCode=1});
